import { AsyncSynapticQueue } from './queue.js';
import { AsyncAxonWorker } from './worker.js';
import { NeuralImpulse, MessageStatus } from './message.js';
import { AsyncWorkerMonitor } from './monitor.js';
import { AsyncErrorHandler } from './error_handler.js';

export class CoreLiteRouter {
    private queues: Map<string, AsyncSynapticQueue> = new Map();
    private workers: Map<string, AsyncAxonWorker> = new Map();
    private isActive: boolean = false;
    public monitor: AsyncWorkerMonitor;
    public errorHandler: AsyncErrorHandler;

    constructor() {
        this.setupBuiltinQueues();
        this.monitor = new AsyncWorkerMonitor();
        this.errorHandler = new AsyncErrorHandler(this);
    }

    /**
     * 注册系统内置强制队列
     * Q_RESPONSE_SINK 为终端队列，不需要 WAL
     */
    private setupBuiltinQueues(): void {
        const builtinQueues = [
            'Q_AUDIT_INPUT',
            'Q_AUDITED_INPUT', // 修复 Python 版本遗漏的问题
            'Q_AUDIT_OUTPUT',
            'Q_ERROR',
            'Q_DONE',
            'Q_REFLECTION' // 后台自我反思队列
        ];

        for (const queueId of builtinQueues) {
            this.queues.set(queueId, new AsyncSynapticQueue(queueId, 1000));
        }

        // 终端队列不需要 WAL（最终归宿，无进一步移交）
        this.queues.set('Q_RESPONSE_SINK', new AsyncSynapticQueue('Q_RESPONSE_SINK', 1000, false));
    }

    /**
     * 手动注册队列（供不需要绑定 Worker 的独立消费端使用）
     */
    public registerQueue(queue: AsyncSynapticQueue): void {
        if (!this.queues.has(queue.queueId)) {
            this.queues.set(queue.queueId, queue);
        }
    }

    /**
     * 注册新的工作器
     */
    public registerWorker(worker: AsyncAxonWorker): void {
        const queueId = worker.getInputQueue().queueId;
        if (!this.queues.has(queueId)) {
            this.queues.set(queueId, worker.getInputQueue());
        }

        this.workers.set(worker.id, worker);
        this.monitor.registerWorker(worker);

        if (this.isActive) {
            worker.start(); // 后台启动事件循环
        }
    }

    /**
     * 启动系统
     */
    public activate(): void {
        if (this.isActive) return;
        this.isActive = true;

        console.log(`[Router] 正在激活 ${this.workers.size} 个工作器...`);
        for (const worker of this.workers.values()) {
            worker.start();
        }

        // 启动系统监控守护进程
        this.monitor.start();
    }

    /**
     * 停止系统
     * 停止顺序：monitor → workers → queues（先停生产消费者，最后停存储层）
     */
    public async stop(): Promise<void> {
        this.isActive = false;

        // 停止监控守护程序
        this.monitor.stop();

        console.log(`[Router] 正在停止 ${this.workers.size} 个工作器...`);
        const stopPromises = Array.from(this.workers.values()).map(w => w.stop());
        await Promise.all(stopPromises);

        console.log('[Router] 所有工作器已停止。');

        // 停止所有队列以 flush WAL 日志
        console.log(`[Router] 正在停止 ${this.queues.size} 个队列...`);
        const queueStopPromises = Array.from(this.queues.values()).map(q => q.stop());
        await Promise.all(queueStopPromises);
        console.log('[Router] 所有队列已停止，WAL 已 flush。');
    }

    /**
     * 外部注入脉冲入口
     */
    public async injectInput(impulse: NeuralImpulse): Promise<boolean> {
        // 强制路由到输入审计队列
        impulse.actionIntent = 'Q_AUDIT_INPUT';
        return this.routeMessage(impulse, 'Q_AUDIT_INPUT');
    }

    /**
     * 核心路由逻辑
     * 成功移交后对来源队列写 Log2（确认消息已安全离开来源队列）
     */
    public async routeMessage(impulse: NeuralImpulse, targetQueueId: string): Promise<boolean> {
        if (!this.isActive) {
            console.warn(`[Router] 系统未激活，拒绝路由消息 ${impulse.messageId}`);
            return false;
        }

        impulse.status = MessageStatus.QUEUED;

        // 📊 消息流动日志：路由追踪
        const sourceAgent = impulse.sourceAgent || 'Unknown';
        const prevQueue = impulse.metadata['current_queue'] || 'External';
        const routeMsg = `🔀 [ROUTE] ${impulse.sessionId} | ${sourceAgent} → ${targetQueueId} | from: ${prevQueue}`;
        console.log(routeMsg);
        globalThis.logRaw?.(routeMsg);

        // 更新当前队列位置
        impulse.metadata['current_queue'] = targetQueueId;
        impulse.metadata['routing_timestamp'] = Date.now();

        // SINK 终点保护机制（使用集中化的校验逻辑）
        if (targetQueueId === 'Q_RESPONSE_SINK') {
            if (!AsyncAxonWorker.isSinkAccessAllowed(impulse.sourceAgent)) {
                const securityMsg = `[ROUTER SECURITY] 尝试直达 SINK 被拦截: source=${impulse.sourceAgent}`;
                console.warn(securityMsg);
                globalThis.logRaw?.(securityMsg);
                targetQueueId = 'Q_ERROR';
                impulse.metadata['routing_error'] = 'Security violation: Direct access to SINK';
            }
        }

        // 处理内部特殊路由逻辑：Audit Input 完毕应该去 BIZ
        if (impulse.sourceAgent === 'AuditInputWorker') {
            if (targetQueueId === 'Q_AUDIT_OUTPUT') {
                // 修复 Python 版本的设计缺陷：输入审计成功后，应该去 Q_AUDITED_INPUT 找业务节点，而不是直接跳到输出审计
                targetQueueId = 'Q_AUDITED_INPUT';
                impulse.actionIntent = targetQueueId;
            }
        }

        let queue = this.queues.get(targetQueueId);
        if (!queue) {
            // 动态创建队列（支持插件形式的临时 Agent 通信）
            // 注意：频繁动态创建可能表示 actionIntent 配置有误，请检查
            console.warn(`[QUEUE] 动态创建新队列: ${targetQueueId} (session: ${impulse.sessionId}, source: ${impulse.sourceAgent})`);
            globalThis.logRaw?.(`[QUEUE] 动态创建新队列: ${targetQueueId}`);
            queue = new AsyncSynapticQueue(targetQueueId, 1000);
            this.queues.set(targetQueueId, queue);
        }

        const result = await queue.asyncPut(impulse);

        // 移交成功：对来源队列写 Log2（确认消息已安全离开来源队列）
        if (result) {
            const srcQueueId = impulse.metadata['_src_queue_id'];
            if (srcQueueId) {
                const srcQueue = this.queues.get(srcQueueId);
                if (srcQueue) {
                    srcQueue.confirmDelivery(impulse);
                }
                delete impulse.metadata['_src_queue_id']; // 清理临时标记
            }
        }

        return result;
    }

    public getQueueMetrics() {
        const queueMetrics: Record<string, any> = {};
        for (const [id, queue] of this.queues.entries()) {
            queueMetrics[id] = queue.getMetrics();
        }

        return {
            queues: queueMetrics,
            workers: this.monitor.getGlobalMetrics()
        };
    }
}
