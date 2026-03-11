import { AsyncSynapticQueue } from './queue.js';
import { AsyncAxonWorker } from './worker.js';
import { NeuralImpulse, MessageStatus } from './message.js';
import { AsyncWorkerMonitor } from './monitor.js';
import { AsyncErrorHandler } from './error_handler.js';

/**
 * 🔥 全局日志函数（由应用层注入）
 */
declare global {
  var logRaw: ((message: string) => void) | undefined;
}

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
     */
    private setupBuiltinQueues(): void {
        const builtinQueues = [
            'Q_AUDIT_INPUT',
            'Q_AUDITED_INPUT', // 修复 Python 版本遗漏的问题
            'Q_AUDIT_OUTPUT',
            'Q_RESPONSE_SINK',
            'Q_ERROR',
            'Q_DONE',
            'Q_REFLECTION' // 后台自我反思队列
        ];

        for (const queueId of builtinQueues) {
            this.queues.set(queueId, new AsyncSynapticQueue(queueId, 1000));
        }
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
     */
    public async stop(): Promise<void> {
        this.isActive = false;

        // 停止监控守护程序
        this.monitor.stop();

        console.log(`[Router] 正在停止 ${this.workers.size} 个工作器...`);
        const stopPromises = Array.from(this.workers.values()).map(w => w.stop());
        await Promise.all(stopPromises);

        console.log('[Router] 所有工作器已停止。');
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

        // SINK 终点保护机制（双重拦截之一，另一个在 Worker 内部）
        if (targetQueueId === 'Q_RESPONSE_SINK') {
            const source = impulse.sourceAgent;
            if (source !== 'Q_AUDIT_OUTPUT' && source !== 'AuditOutputWorker') {
                const securityMsg = `[ROUTER SECURITY] 尝试直达 SINK 被拦截: source=${source}`;
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
            const createMsg = `📦 [QUEUE] 动态创建新队列: ${targetQueueId}`;
            console.log(createMsg);
            globalThis.logRaw?.(createMsg);
            queue = new AsyncSynapticQueue(targetQueueId, 1000);
            this.queues.set(targetQueueId, queue);
        }

        return await queue.asyncPut(impulse);
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
