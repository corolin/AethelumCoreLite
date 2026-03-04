import { AsyncSynapticQueue } from './queue.js';
import { NeuralImpulse, MessageStatus } from './message.js';
import { AsyncHookChain } from '../hooks/chain.js';
import { HookType } from '../hooks/types.js';
import type { HookContext } from '../hooks/types.js';
import { CoreLiteRouter } from './router.js';

export enum WorkerState {
    INITIALIZING = 'initializing',
    RUNNING = 'running',
    PAUSED = 'paused',
    STOPPING = 'stopping',
    STOPPED = 'stopped',
    ERROR = 'error'
}

export class AsyncAxonWorker {
    public id: string;
    public state: WorkerState;

    private inputQueue: AsyncSynapticQueue;
    private router: CoreLiteRouter;

    private preHooks: AsyncHookChain;
    private postHooks: AsyncHookChain;
    private errorHooks: AsyncHookChain;

    private stopRequested: boolean = false;
    private isProcessing: boolean = false;

    // ==== 监控与恢复专用指标 ====
    private internalErrorCount: number = 0;
    private lastActiveTimestamp: number = Date.now();
    private processedCount: number = 0;

    constructor(id: string, inputQueue: AsyncSynapticQueue, router: CoreLiteRouter) {
        this.id = id;
        this.inputQueue = inputQueue;
        this.router = router;

        this.state = WorkerState.INITIALIZING;

        this.preHooks = new AsyncHookChain(`${id}_pre`);
        this.postHooks = new AsyncHookChain(`${id}_post`);
        this.errorHooks = new AsyncHookChain(`${id}_error`);
    }

    public getPreHooks(): AsyncHookChain { return this.preHooks; }
    public getPostHooks(): AsyncHookChain { return this.postHooks; }
    public getErrorHooks(): AsyncHookChain { return this.errorHooks; }
    public getInputQueue(): AsyncSynapticQueue { return this.inputQueue; }

    // 暴露给 Monitor 采集的指标
    public getInternalErrorCount(): number { return this.internalErrorCount; }
    public getLastActiveTime(): number { return this.lastActiveTimestamp; }
    public getProcessedCount(): number { return this.processedCount; }

    /**
     * 启动 Worker
     */
    public async start(): Promise<void> {
        if (this.state === WorkerState.RUNNING) return;

        this.state = WorkerState.RUNNING;
        this.stopRequested = false;

        // 不再 await 这个调用，让它在后台循环
        this.runLoop().catch(err => {
            console.error(`[Worker ${this.id}] 发生致命错误:`, err);
            this.state = WorkerState.ERROR;
        });
    }

    /**
     * 停止 Worker
     */
    public async stop(): Promise<void> {
        this.stopRequested = true;
        this.state = WorkerState.STOPPING;

        // 给一些时间让正在处理的消息完成
        let maxWait = 50; // 50 * 100ms = 5s
        while (this.isProcessing && maxWait > 0) {
            await new Promise(resolve => setTimeout(resolve, 100));
            maxWait--;
        }

        this.state = WorkerState.STOPPED;
    }

    /**
     * Worker 主循环 - 基于 Node.js 事件循环的自然异步等待
     */
    private async runLoop(): Promise<void> {
        console.log(`[Worker ${this.id}] 启动并在队列 ${this.inputQueue.queueId} 上监听...`);

        while (!this.stopRequested) {
            try {
                if (this.state === WorkerState.PAUSED) {
                    await new Promise(resolve => setTimeout(resolve, 500));
                    continue;
                }

                // 遇到 ERROR 挂起状态（被 Monitor 熔断隔离），挂起并等待 AutoRecovery 拉起
                if (this.state === WorkerState.ERROR) {
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    continue;
                }

                // 天然异步等待，不阻塞 Node.js 其他事件循环任务
                // 设置一个超时，以便可以响应 stopRequested
                const impulse = await this.inputQueue.asyncGet(1000);

                // 刷新活跃心跳
                this.lastActiveTimestamp = Date.now();

                if (!impulse) {
                    continue; // Timeout 或 null
                }

                this.isProcessing = true;
                await this.processImpulse(impulse);
                this.processedCount++;
                this.isProcessing = false;

            } catch (err) {
                this.internalErrorCount++;
                console.error(`[Worker ${this.id}] 处理循环异常:`, err);
                // 短暂延迟防止死循环吃满 CPU
                await new Promise(resolve => setTimeout(resolve, 1000));
            } finally {
                this.isProcessing = false;
            }
        }

        console.log(`[Worker ${this.id}] 已停止。`);
    }

    /**
     * 处理单个消息
     */
    private async processImpulse(impulse: NeuralImpulse): Promise<void> {
        const context: HookContext = {
            workerId: this.id,
            queueId: this.inputQueue.queueId,
            timestamp: Date.now()
        };

        try {
            impulse.status = MessageStatus.PROCESSING;

            // 1. SINK 安全校验
            if (!this.validateSinkSecurity(impulse)) {
                impulse.actionIntent = 'Q_ERROR';
                impulse.metadata['error_message'] = 'SINK_SECURITY_VIOLATION';
                await this.router.routeMessage(impulse, 'Q_ERROR');
                return;
            }

            // 2. Pre Hooks 执行
            const preResult = await this.preHooks.executeHooks(impulse, HookType.PRE_PROCESS, context);
            if (!preResult) return; // 拦截

            // 3. (Core Logic 占位，主要是给 Hook 执行的)
            let processedImpulse = preResult;

            // 4. Post Hooks 执行
            const postResult = await this.postHooks.executeHooks(processedImpulse, HookType.POST_PROCESS, context);
            if (!postResult) return; // 拦截

            processedImpulse = postResult;
            processedImpulse.status = MessageStatus.COMPLETED;

            // 5. 路由下一步
            const targetQueue = processedImpulse.actionIntent;
            if (targetQueue && targetQueue !== 'Done' && targetQueue !== 'Q_DONE') {
                processedImpulse.updateSource(this.id);
                await this.router.routeMessage(processedImpulse, targetQueue);
            }

        } catch (err: any) {
            impulse.status = MessageStatus.FAILED;
            this.internalErrorCount++;

            const errorContext = {
                ...context,
                error: err,
                stage: 'execute_process'
            };

            await this.router.errorHandler.handleError(err as Error, impulse, errorContext);

            try {
                // 执行 Error Hooks
                const errorResult = await this.errorHooks.executeHooks(impulse, HookType.ERROR_HANDLER, errorContext);
                if (errorResult && errorResult.actionIntent !== 'Q_ERROR') {
                    // 尝试路由到错误处理队列
                    await this.router.routeMessage(errorResult, errorResult.actionIntent || 'Q_ERROR');
                }
            } catch (fatalErr) {
                console.error(`[Worker ${this.id}] ErrorHook 也发生致命错误:`, fatalErr);
            }
        }
    }

    /**
     * 严格的 SINK 安全校验 (参照原版的双重保障机制)
     */
    private validateSinkSecurity(impulse: NeuralImpulse): boolean {
        const originalIntent = impulse.actionIntent;

        // 如果目标是最终响应队列 Q_RESPONSE_SINK
        if (originalIntent === 'Q_RESPONSE_SINK') {
            const source = impulse.sourceAgent;

            // Node.js 版本简化：只要源头不是经过 Output 审计，就不允许直达 SINK
            // 这里确保业务 Agent 不能绕过 Audited Output 直接发送响应
            if (source !== 'Q_AUDIT_OUTPUT' && source !== 'AuditOutputWorker') {
                console.warn(`[SECURITY VIOLATION] Worker ${this.id} 拒绝非法访问: ${source} 试图绕过审计直达 Q_RESPONSE_SINK`);
                return false;
            }
        }

        return true;
    }
}
