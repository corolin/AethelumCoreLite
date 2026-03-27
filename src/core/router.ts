import { AsyncSynapticQueue } from './queue.js';
import { AsyncAxonWorker } from './worker.js';
import { NeuralImpulse, MessageStatus } from './message.js';
import { AsyncWorkerMonitor } from './monitor.js';
import { AsyncErrorHandler } from './error_handler.js';
import { getStructuredLogger } from '../utils/structured_logger.js';

const routerLogger = getStructuredLogger('CoreLiteRouter');

/**
 * 路由层日志统一走 {@link routerLogger}（结构化，便于聚合）；`globalThis.logRaw` 为可选旁路。
 * 本模块不使用 `console.*`，避免与结构化管道混用。
 */
function emitRouterLog(
    level: 'info' | 'warning',
    message: string,
    metadata: Record<string, unknown>,
    rawLine?: string,
): void {
    if (level === 'warning') {
        routerLogger.warning(message, { metadata });
    } else {
        routerLogger.info(message, { metadata });
    }
    globalThis.logRaw?.(rawLine ?? message);
}

export class CoreLiteRouter {
    private queues: Map<string, AsyncSynapticQueue> = new Map();
    private workers: Map<string, AsyncAxonWorker> = new Map();
    private isActive: boolean = false;
    private enableWal: boolean;
    public monitor: AsyncWorkerMonitor;
    public errorHandler: AsyncErrorHandler;

    constructor(enableWal: boolean = true) {
        this.enableWal = enableWal;
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
            'Q_REFLECTION' // 后台自我反思队列
        ];

        for (const queueId of builtinQueues) {
            this.queues.set(queueId, new AsyncSynapticQueue(queueId, 1000, this.enableWal));
        }

        // 终端队列不需要 WAL（最终归宿，无进一步移交）
        this.queues.set('Q_DONE', new AsyncSynapticQueue('Q_DONE', 1000, false));
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

        emitRouterLog('info', `[Router] 正在激活 ${this.workers.size} 个工作器...`, {
            event: 'router.activate',
            workerCount: this.workers.size,
        });
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

        emitRouterLog('info', `[Router] 正在停止 ${this.workers.size} 个工作器...`, {
            event: 'router.stop',
            phase: 'workers',
            workerCount: this.workers.size,
        });
        const stopPromises = Array.from(this.workers.values()).map(w => w.stop());
        await Promise.all(stopPromises);

        emitRouterLog('info', '[Router] 所有工作器已停止。', {
            event: 'router.stop',
            phase: 'workers_done',
        });

        // 停止所有队列以 flush WAL 日志
        emitRouterLog('info', `[Router] 正在停止 ${this.queues.size} 个队列...`, {
            event: 'router.stop',
            phase: 'queues',
            queueCount: this.queues.size,
        });
        const queueStopPromises = Array.from(this.queues.values()).map(q => q.stop());
        await Promise.all(queueStopPromises);
        emitRouterLog('info', '[Router] 所有队列已停止，WAL 已 flush。', {
            event: 'router.stop',
            phase: 'complete',
        });
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
     * 成功移交后对来源队列写 WAL tombstone（confirmDelivery，确认消息已安全离开来源队列）
     */
    public async routeMessage(impulse: NeuralImpulse, targetQueueId: string): Promise<boolean> {
        if (!this.isActive) {
            emitRouterLog('warning', `[Router] 系统未激活，拒绝路由消息 ${impulse.messageId}`, {
                event: 'router.route',
                rejected: true,
                messageId: impulse.messageId,
            });
            return false;
        }

        impulse.status = MessageStatus.QUEUED;

        // 📊 消息流动日志：路由追踪
        const sourceAgent = impulse.sourceAgent || 'Unknown';
        const prevQueue = impulse.metadata['current_queue'] || 'External';
        const routeMsg = `🔀 [ROUTE] ${impulse.sessionId} | ${sourceAgent} → ${targetQueueId} | from: ${prevQueue}`;
        emitRouterLog('info', routeMsg, {
            event: 'route',
            sessionId: impulse.sessionId,
            sourceAgent,
            targetQueue: targetQueueId,
            fromQueue: prevQueue,
        });

        // 更新当前队列位置
        impulse.metadata['current_queue'] = targetQueueId;
        impulse.metadata['routing_timestamp'] = Date.now();

        // SINK 终点保护机制（使用集中化的校验逻辑）
        if (targetQueueId === 'Q_RESPONSE_SINK') {
            if (!AsyncAxonWorker.isSinkAccessAllowed(impulse.sourceAgent)) {
                const securityMsg = `[ROUTER SECURITY] 尝试直达 SINK 被拦截: source=${impulse.sourceAgent}`;
                emitRouterLog('warning', securityMsg, {
                    event: 'router.security',
                    sourceAgent: impulse.sourceAgent,
                });
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
            emitRouterLog(
                'warning',
                `[QUEUE] 动态创建新队列: ${targetQueueId} (session: ${impulse.sessionId}, source: ${impulse.sourceAgent})`,
                {
                    event: 'router.dynamic_queue',
                    targetQueueId,
                    sessionId: impulse.sessionId,
                    sourceAgent: impulse.sourceAgent,
                },
                `[QUEUE] 动态创建新队列: ${targetQueueId}`,
            );
            queue = new AsyncSynapticQueue(targetQueueId, 1000, this.enableWal);
            this.queues.set(targetQueueId, queue);
        }

        // 入目标队列前先快照“上一跳来源队列”信息。
        // 目标队列若走“直接投递给等待消费者”路径，可能会覆写 _src_* 为目标队列自身；
        // 若不快照，confirmDelivery 可能删错 WAL 或漏删上一跳 WAL。
        const prevSrcQueueId = impulse.metadata['_src_queue_id'] as string | undefined;
        const prevSrcLsn = impulse.metadata['_src_wal_lsn'] as number | undefined;

        const result = await queue.asyncPut(impulse);

        // 移交成功：对来源队列 confirmDelivery（WAL tombstone）
        if (result) {
            if (prevSrcQueueId) {
                const srcQueue = this.queues.get(prevSrcQueueId);
                if (srcQueue) {
                    // 必须使用“入队前快照”的来源位点，避免被目标队列覆盖。
                    srcQueue.confirmDelivery(impulse, prevSrcLsn);
                }
                // 仅清理旧标记；若目标队列已写入新的 _src_*（用于下一跳），不能误删。
                if (impulse.metadata['_src_queue_id'] === prevSrcQueueId) {
                    delete impulse.metadata['_src_queue_id'];
                }
                if (impulse.metadata['_src_wal_lsn'] === prevSrcLsn) {
                    delete impulse.metadata['_src_wal_lsn'];
                }
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
