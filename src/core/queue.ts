import { NeuralImpulse } from './message.js';
// WAL：移交/过期用 writeDelete；旧版 writeLog2 仅保留于 ImprovedWALWriter（tracker.ptr 兼容）
import { ImprovedWALWriter } from '../utils/wal_writer.js';
import type { WALRecoveredEntry } from '../utils/wal_writer.js';

export interface QueueMetrics {
    queueId: string;
    size: number;
    capacity: number;
    totalMessages: number;
    totalDropped: number;
}

export class AsyncSynapticQueue {
    public queueId: string;
    public maxSize: number;

    // 使用数组模拟优先级队列 (0: CRITICAL -> 4: BACKGROUND)
    private queues: NeuralImpulse[][];

    // Pending consumers waiting for a message
    private waitingConsumers: Array<{
        resolve: (message: NeuralImpulse | null) => void;
        timeoutId?: NodeJS.Timeout | undefined;
    }> = [];

    private metrics: QueueMetrics;
    private walWriter: ImprovedWALWriter | null = null;
    private enableWal: boolean;
    private walReady: Promise<void> | null = null;
    public autoExpand: boolean;
    private baseCapacity: number;
    private shrinkTimer: NodeJS.Timeout | null = null;

    constructor(queueId: string, maxSize: number = 0, enableWal: boolean = true, autoExpand: boolean = true, shrinkIntervalMs: number = 10 * 60 * 1000) {
        this.queueId = queueId;
        this.maxSize = maxSize;
        this.autoExpand = autoExpand;
        this.baseCapacity = maxSize;
        this.enableWal = enableWal;

        if (this.enableWal) {
            this.walWriter = new ImprovedWALWriter(queueId, "wal_data_v2", true);
            // 异步初始化 WAL 并恢复未提交消息，不阻塞队列构造
            this.walReady = this.walWriter.start()
                .then((recoveredEntries) => {
                    for (const entry of recoveredEntries) {
                        this.replayEntry(entry);
                    }
                    if (recoveredEntries.length > 0) {
                        console.log(`[QUEUE ${queueId}] 已恢复 ${recoveredEntries.length} 条消息`);
                    }
                })
                .catch(err => {
                    console.error(`[QUEUE ${queueId}] WAL 初始化失败，降级为无 WAL 模式:`, err);
                    this.walWriter = null;
                });
        }

        // 初始化 5 个优先级队列
        this.queues = Array.from({ length: 5 }, () => []);

        this.metrics = {
            queueId,
            size: 0,
            capacity: maxSize,
            totalMessages: 0,
            totalDropped: 0
        };

        // 启动定时缩容检查
        this.startShrinkTimer(shrinkIntervalMs);
    }

    /**
     * 异步放入消息 (零锁设计，天然线程安全)
     */
    public async asyncPut(item: NeuralImpulse): Promise<boolean> {
        if (this.maxSize > 0 && this.metrics.size >= this.maxSize) {
            if (this.autoExpand) {
                // 动态扩容：每次增加 10%
                this.maxSize = Math.ceil(this.maxSize * 1.1);
                this.metrics.capacity = this.maxSize;
                console.log(`[QUEUE ${this.queueId}] 动态扩容至 ${this.maxSize}`);
            } else {
                // 不自动扩容，拒绝入队
                this.metrics.totalDropped++;
                return false;
            }
        }

        // 乐观递增：在 await 之前预留容量槽位，防止并发 asyncPut 超过 maxSize
        this.metrics.size++;

        const priority = item.priority;

        // 优先级越界钳位
        const clampedPriority = Math.max(0, Math.min(4, priority));

        try {
            let lsn: number | null = null;
            // 等待 WAL 初始化+恢复完成（如果正在初始化中）
            if (this.walReady) {
                await this.walReady;
            }
            if (this.walWriter) {
                // Write to WAL Log1 before processing
                lsn = await this.walWriter.writeLog1(item.messageId, priority, item.toDict());
                item.metadata['wal_lsn'] = lsn;
            }

            // 📊 消息流动日志：入队
            const fromAgent = item.sourceAgent || 'Unknown';
            const enqueueMsg = `⬇️  [ENQUEUE] ${item.sessionId} | ${fromAgent} → ${this.queueId} | size: ${this.metrics.size}`;
            console.log(enqueueMsg);
            globalThis.logRaw?.(enqueueMsg);

            // 如果有等待的消费者，直接将消息交给列表中的第一个（最老的）消费者
            if (this.waitingConsumers.length > 0) {
                const consumer = this.waitingConsumers.shift()!;
                if (consumer.timeoutId) {
                    clearTimeout(consumer.timeoutId);
                }
                this.metrics.size--; // 直接投递不占队列位置，回滚乐观递增
                this.metrics.totalMessages++;
                const directMsg = `⚡ [DEQUEUE] ${item.sessionId} | ${this.queueId} → 直接投递给等待消费者`;
                console.log(directMsg);
                globalThis.logRaw?.(directMsg);
                // 直接投递路径也需要记录来源信息，确保 Router 能正确写 Log2
                // wal_lsn 此时还是本队列的值，必须在 consumer.resolve 前保存
                item.metadata['_src_queue_id'] = this.queueId;
                item.metadata['_src_wal_lsn'] = lsn ?? item.metadata['wal_lsn'];
                consumer.resolve(item);
                return true;
            }

            // 否则放入对应的优先级队列
            this.queues[clampedPriority]!.push(item);
            this.metrics.totalMessages++;

            return true;
        } catch (err) {
            // WAL 写入失败时回滚乐观递增
            this.metrics.size--;
            throw err;
        }
    }

    /**
     * 异步获取消息
     * 注意：取出消息时不写 Log2，Log2 由 Router 在移交成功后通过 confirmDelivery() 触发
     * @param timeoutMs 超时时间（毫秒），可选
     */
    public async asyncGet(timeoutMs?: number): Promise<NeuralImpulse | null> {
        // 1. 使用循环遍历优先级队列，跳过过期消息（避免递归栈溢出）
        while (true) {
            let foundExpired = false;
            for (let i = 0; i < 5; i++) {
                if (this.queues[i]!.length > 0) {
                    const item = this.queues[i]!.shift();
                    if (!item) continue;
                    this.metrics.size--;

                    // 跳过已过期的消息，继续循环查找下一个
                    if (item.isExpired()) {
                        const expireMsg = `⏰ [DEQUEUE] ${item.sessionId} | ${this.queueId} → 消息已过期，丢弃`;
                        console.log(expireMsg);
                        globalThis.logRaw?.(expireMsg);
                        // 过期消息直接丢弃，写入 tombstone 释放 WAL 所有权
                        // （过期消息不会经过 Router，无法由 confirmDelivery 触发）
                        if (this.walWriter && item.metadata['wal_lsn'] !== undefined) {
                            await this.walWriter.writeDelete(item.metadata['wal_lsn'] as number);
                        }
                        foundExpired = true;
                        break; // 跳出 for 循环，重新从头遍历优先级
                    }

                    // 记录来源队列 ID 和当前 LSN，供 Router 在移交成功后写 Log2
                    // 必须在此处保存 wal_lsn，因为消息进入下一个队列后 wal_lsn 会被覆盖
                    item.metadata['_src_queue_id'] = this.queueId;
                    item.metadata['_src_wal_lsn'] = item.metadata['wal_lsn'];

                    // 消息流动日志：出队
                    const dequeueMsg = `⬆️  [DEQUEUE] ${item.sessionId} | ${this.queueId} → Worker | remaining: ${this.metrics.size}`;
                    console.log(dequeueMsg);
                    globalThis.logRaw?.(dequeueMsg);

                    return item;
                }
            }
            // 所有队列都空或刚消费完一个过期消息但队列还有剩余
            if (!foundExpired) break;
        }

        // 2. 队列为空，等待新消息到来
        // 🔥 不输出等待日志，减少日志噪音
        return new Promise((resolve) => {
            const consumer = { resolve, timeoutId: undefined as NodeJS.Timeout | undefined };

            if (timeoutMs) {
                consumer.timeoutId = setTimeout(() => {
                    // 超时处理：从等待队列中移除消费者并返回 null
                    const index = this.waitingConsumers.indexOf(consumer);
                    if (index !== -1) {
                        this.waitingConsumers.splice(index, 1);
                    }
                    // 🔥 不输出超时日志，减少日志噪音
                    resolve(null);
                }, timeoutMs);
            }

            this.waitingConsumers.push(consumer);
        });
    }

    /**
     * 移交成功确认：Router 在消息成功放入目标队列后调用
     * 向来源队列的 WAL 写入 tombstone（DEL 标记），释放消息所有权
     *
     * @param item 消息对象
     * @param explicitLsn 来源队列的 LSN（Router 应传入 `impulse.metadata['_src_wal_lsn']`）
     *   **禁止**使用 `item.metadata['wal_lsn']` 作为来源 LSN：移交成功后该字段已是**目标队列**的 LSN，
     *   误用会 tombstone 错误记录。若未传 `explicitLsn`，仅回退到 `item.metadata['_src_wal_lsn']`；
     *   二者皆缺则跳过并告警（绝不回退到 `wal_lsn`）。
     */
    public async confirmDelivery(item: NeuralImpulse, explicitLsn?: number): Promise<void> {
        const fromMeta = item.metadata['_src_wal_lsn'] as number | undefined;
        const lsn = explicitLsn !== undefined && explicitLsn !== null ? explicitLsn : fromMeta;

        if (this.walWriter && (lsn === undefined || lsn === null)) {
            console.warn(
                `[QUEUE ${this.queueId}] confirmDelivery 跳过：缺少来源 LSN（需 explicitLsn 或 metadata._src_wal_lsn；` +
                    `勿使用 wal_lsn，移交后已为目标队列 LSN） messageId=${item.messageId}`,
            );
            return;
        }

        if (this.walWriter && lsn !== undefined && lsn !== null) {
            await this.walWriter.writeDelete(lsn as number);
        }
    }

    public size(): number {
        return this.metrics.size;
    }

    public empty(): boolean {
        return this.metrics.size === 0;
    }

    public getMetrics(): QueueMetrics {
        return { ...this.metrics }; // 返回副本
    }

    public clear(): void {
        this.queues = Array.from({ length: 5 }, () => []);
        this.metrics.size = 0;

        // Resolve all waiting consumers with null
        const consumers = this.waitingConsumers;
        this.waitingConsumers = [];
        for (const c of consumers) {
            if (c.timeoutId) clearTimeout(c.timeoutId);
            c.resolve(null);
        }
    }

    public async stop(): Promise<void> {
        if (this.shrinkTimer) {
            clearInterval(this.shrinkTimer);
            this.shrinkTimer = null;
        }
        if (this.walWriter) {
            await this.walWriter.stop();
        }
    }

    // ============== 崩溃恢复 ==============

    /**
     * 定时缩容检查：每 10 分钟检查一次，如果队列大小低于基准容量，缩回基准
     */
    private startShrinkTimer(intervalMs: number): void {
        if (this.maxSize <= 0) return; // 无上限的队列不需要
        this.shrinkTimer = setInterval(() => {
            this.checkShrink();
        }, intervalMs).unref();
    }

    /**
     * 内部缩容逻辑
     */
    private checkShrink(): void {
        if (this.maxSize > this.baseCapacity && this.metrics.size < this.baseCapacity) {
            this.maxSize = this.baseCapacity;
            this.metrics.capacity = this.maxSize;
            console.log(`[QUEUE ${this.queueId}] 缩容回基准容量 ${this.maxSize}`);
        }
    }

    /**
     * 回放单条 WAL 记录到队列（不写 WAL，已有 LSN）
     */
    private replayEntry(entry: WALRecoveredEntry): void {
        try {
            const dict = JSON.parse(entry.payload);
            const item = NeuralImpulse.fromDict(dict);
            item.metadata['wal_lsn'] = entry.lsn;

            const clampedPriority = Math.max(0, Math.min(4, dict.priority ?? 2));
            this.queues[clampedPriority]!.push(item);
            this.metrics.size++;
            this.metrics.totalMessages++;
        } catch (err) {
            console.warn(`[QUEUE ${this.queueId}] 恢复 LSN ${entry.lsn} 失败，跳过:`, err);
        }
    }
}
