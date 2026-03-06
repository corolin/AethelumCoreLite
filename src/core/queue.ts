import { NeuralImpulse, MessagePriority } from './message.js';
import { ImprovedWALWriter } from '../utils/wal_writer.js';

/**
 * 🔥 全局日志函数（由应用层注入）
 */
declare global {
  var logRaw: ((message: string) => void) | undefined;
}

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

    constructor(queueId: string, maxSize: number = 0, enableWal: boolean = true) {
        this.queueId = queueId;
        this.maxSize = maxSize;
        this.enableWal = enableWal;

        if (this.enableWal) {
            this.walWriter = new ImprovedWALWriter(queueId, "wal_data_v2", true);
            this.walWriter.start();
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
    }

    /**
     * 异步放入消息 (零锁设计，天然线程安全)
     */
    public async asyncPut(item: NeuralImpulse): Promise<boolean> {
        if (this.maxSize > 0 && this.metrics.size >= this.maxSize) {
            this.metrics.totalDropped++;
            console.warn(`⚠️  [QUEUE] ${this.queueId} 队列已满，丢弃消息 ${item.messageId}`);
            return false; // Queue full
        }

        const priority = item.priority;

        let lsn: number | null = null;
        if (this.walWriter) {
            // Write to WAL Log1 before processing
            lsn = await this.walWriter.writeLog1(item.messageId, priority, item.toDict());
            item.metadata['wal_lsn'] = lsn;
        }

        // 📊 消息流动日志：入队
        const fromAgent = item.sourceAgent || 'Unknown';
        const enqueueMsg = `⬇️  [ENQUEUE] ${item.sessionId} | ${fromAgent} → ${this.queueId} | size: ${this.metrics.size + 1}`;
        console.log(enqueueMsg);
        globalThis.logRaw?.(enqueueMsg);

        // 如果有等待的消费者，直接将消息交给列表中的第一个（最老的）消费者
        if (this.waitingConsumers.length > 0) {
            const consumer = this.waitingConsumers.shift()!;
            if (consumer.timeoutId) {
                clearTimeout(consumer.timeoutId);
            }
            this.metrics.totalMessages++;
            const directMsg = `⚡ [DEQUEUE] ${item.sessionId} | ${this.queueId} → 直接投递给等待消费者`;
            console.log(directMsg);
            globalThis.logRaw?.(directMsg);
            consumer.resolve(item);
            return true;
        }

        // 否则放入对应的优先级队列
        this.queues[priority]!.push(item);
        this.metrics.size++;
        this.metrics.totalMessages++;

        return true;
    }

    /**
     * 异步获取消息
     * @param timeoutMs 超时时间（毫秒），可选
     */
    public async asyncGet(timeoutMs?: number): Promise<NeuralImpulse | null> {
        // 1. 先检查队列中是否有现成消息
        for (let i = 0; i < 5; i++) {
            if (this.queues[i]!.length > 0) {
                // 先入先出 (FIFO) 对于同一优先级的队列
                const item = this.queues[i]!.shift();
                if (!item) continue;
                this.metrics.size--;

                // 跳过已过期的消息
                if (item && item.isExpired()) {
                    const expireMsg = `⏰ [DEQUEUE] ${item.sessionId} | ${this.queueId} → 消息已过期，丢弃`;
                    console.log(expireMsg);
                    globalThis.logRaw?.(expireMsg);
                    if (this.walWriter && item.metadata['wal_lsn']) {
                        // Mark as processed if expired
                        this.walWriter.writeLog2(item.messageId, item.metadata['wal_lsn']);
                    }
                    return this.asyncGet(timeoutMs); // 递归查找下一个
                }

                if (item && this.walWriter && item.metadata['wal_lsn']) {
                    // Node.js doesn't have Python's task_done out of the box so we commit LSN right on retrieval
                    // Assuming reliable delivery by downstream hook chain/error loop.
                    this.walWriter.writeLog2(item.messageId, item.metadata['wal_lsn']);
                }

                // 📊 消息流动日志：出队
                const dequeueMsg = `⬆️  [DEQUEUE] ${item.sessionId} | ${this.queueId} → Worker | remaining: ${this.metrics.size}`;
                console.log(dequeueMsg);
                globalThis.logRaw?.(dequeueMsg);

                return item || null;
            }
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

    public stop(): void {
        if (this.walWriter) {
            this.walWriter.stop();
        }
    }
}
