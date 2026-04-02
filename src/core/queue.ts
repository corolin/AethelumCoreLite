import { NeuralImpulse } from './message.js';
import { AsyncHookChain } from '../hooks/chain.js';
import { HookType } from '../hooks/types.js';
import {
    createQueuePluginMount,
    disposeHookPluginDisposers,
    type HookPluginAttachResult,
    type HookPluginMount,
    type HookPluginRegistry,
    type HookPluginSpec,
} from '../hooks/runtime.js';
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
    private hooks: AsyncHookChain;
    public autoExpand: boolean;
    private baseCapacity: number;
    private shrinkTimer: NodeJS.Timeout | null = null;
    private pluginDisposers: Array<() => void | Promise<void>> = [];

    constructor(queueId: string, maxSize: number = 0, autoExpand: boolean = true, shrinkIntervalMs: number = 10 * 60 * 1000) {
        this.queueId = queueId;
        this.maxSize = maxSize;
        this.autoExpand = autoExpand;
        this.baseCapacity = maxSize;
        this.hooks = new AsyncHookChain(`${queueId}_hooks`);

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

    public getHooks(): AsyncHookChain {
        return this.hooks;
    }

    public async attachHookPlugins(
        registry: HookPluginRegistry,
        specs: HookPluginSpec[],
        mount: Partial<HookPluginMount> = {},
    ): Promise<HookPluginAttachResult> {
        const result = await registry.resolve(createQueuePluginMount(this, mount), specs);
        this.hooks.addHooks(result.hooks);
        this.pluginDisposers.push(...result.disposers);
        return result;
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
            // 执行 BEFORE_PUT 钩子 (例如：WAL 写入、数据清洗、审计)
            const context = {
                queueId: this.queueId,
                timestamp: Date.now(),
                stage: 'put'
            };

            const processedItem = await this.hooks.executeHooks(item, HookType.QUEUE_BEFORE_PUT, context);
            if (!processedItem) {
                // 如果钩子返回 null，视为该消息被拦截，丢弃之
                this.metrics.size--;
                this.metrics.totalDropped++;
                return true; // 虽然被拦截，但对调用方来说已“处理”完成
            }

            const impulseToPut = processedItem;

            // 📊 消息流动日志：入队
            const fromAgent = impulseToPut.sourceAgent || 'Unknown';
            const enqueueMsg = `⬇️  [ENQUEUE] ${impulseToPut.sessionId} | ${fromAgent} → ${this.queueId} | size: ${this.metrics.size}`;
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
                const directMsg = `⚡ [DEQUEUE] ${impulseToPut.sessionId} | ${this.queueId} → 直接投递给等待消费者`;
                console.log(directMsg);
                globalThis.logRaw?.(directMsg);
                // 直接投递路径也需要记录来源信息，确保 Router 能正确写 Log2 (via AFTER_ACK Hooks)
                impulseToPut.metadata['_src_queue_id'] = this.queueId;
                consumer.resolve(impulseToPut);
                return true;
            }

            // 否则放入对应的优先级队列
            this.queues[clampedPriority]!.push(impulseToPut);
            this.metrics.totalMessages++;

            return true;
        } catch (err) {
            // 钩子失败时回滚乐观递增
            this.metrics.size--;
            throw err;
        }
    }

    /**
     * 异步获取消息
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
                        
                        // 过期消息直接丢弃，触发确认钩子以释放资源（如 WAL tombstone）
                        await this.confirmDelivery(item);
                        
                        foundExpired = true;
                        break; // 跳出 for 循环，重新从头遍历优先级
                    }

                    // 记录来源队列 ID，供 Router/Worker 在移交完成后确认
                    item.metadata['_src_queue_id'] = this.queueId;

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
        return new Promise((resolve) => {
            const consumer = { resolve, timeoutId: undefined as NodeJS.Timeout | undefined };

            if (timeoutMs) {
                consumer.timeoutId = setTimeout(() => {
                    const index = this.waitingConsumers.indexOf(consumer);
                    if (index !== -1) {
                        this.waitingConsumers.splice(index, 1);
                    }
                    resolve(null);
                }, timeoutMs);
            }

            this.waitingConsumers.push(consumer);
        });
    }

    /**
     * 移交成功确认：Router 在消息成功放入目标队列后调用
     * 或者 Worker 在处理完消息（终点站）后调用
     */
    public async confirmDelivery(item: NeuralImpulse, explicitLsn?: number): Promise<void> {
        // 执行 AFTER_ACK 钩子 (例如：WAL writeDelete / PostgreSQL COMMIT)
        const context = {
            queueId: this.queueId,
            timestamp: Date.now(),
            stage: 'confirm',
            explicitLsn: explicitLsn // 用于保留对 WAL lsn 的向下兼容支持
        };

        await this.hooks.executeHooks(item, HookType.QUEUE_AFTER_ACK, context);
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
        // 关键改进：停止时立刻唤醒所有在排队等待消息的 Consumer (Worker)
        this.clear();
        await disposeHookPluginDisposers(this.pluginDisposers);
    }

    // ============== 崩溃恢复 ==============

    /**
     * 定时缩容检查
     */
    private startShrinkTimer(intervalMs: number): void {
        if (this.maxSize <= 0) return; 
        this.shrinkTimer = setInterval(() => {
            this.checkShrink();
        }, intervalMs).unref();
    }

    private checkShrink(): void {
        if (this.maxSize > this.baseCapacity && this.metrics.size < this.baseCapacity) {
            this.maxSize = this.baseCapacity;
            this.metrics.capacity = this.maxSize;
            console.log(`[QUEUE ${this.queueId}] 缩容回基准容量 ${this.maxSize}`);
        }
    }

    /**
     * 回放单条 WAL 记录到队列
     */
    public internalReplay(entry: WALRecoveredEntry): void {
        try {
            const dict = JSON.parse(entry.payload);
            const item = NeuralImpulse.fromDict(dict);
            // 恢复 LSN，以便后续确认时能正确删除
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
