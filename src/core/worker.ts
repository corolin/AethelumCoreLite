import { AsyncSynapticQueue } from './queue.js';
import { NeuralImpulse, MessageStatus } from './message.js';
import { AsyncHookChain } from '../hooks/chain.js';
import { HookType } from '../hooks/types.js';
import type { HookContext } from '../hooks/types.js';
import { CoreLiteRouter } from './router.js';

/**
 * 🔥 全局日志函数（由应用层注入）
 */
declare global {
  var logRaw: ((message: string) => void) | undefined;
}

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

    // 🔥 路由追踪：检测子类是否手动路由过消息
    private hasManuallyRouted: boolean = false;
    private originalRouter: CoreLiteRouter;

    constructor(id: string, inputQueue: AsyncSynapticQueue, router: CoreLiteRouter) {
        this.id = id;
        this.inputQueue = inputQueue;
        this.originalRouter = router;

        // 🔥 创建代理 Router，自动检测子类的路由调用
        this.router = this._createProxiedRouter(router);

        this.state = WorkerState.INITIALIZING;

        this.preHooks = new AsyncHookChain(`${id}_pre`);
        this.postHooks = new AsyncHookChain(`${id}_post`);
        this.errorHooks = new AsyncHookChain(`${id}_error`);
    }

    /**
     * 🔥 创建代理 Router，自动标记子类已手动路由
     *
     * 当子类调用 this.router.routeMessage() 时，
     * 代理会自动设置 hasManuallyRouted = true，
     * 防止基类 processImpulse() 再次路由。
     */
    private _createProxiedRouter(router: CoreLiteRouter): CoreLiteRouter {
        // 🔥 捕获正确的 this 引用（Worker 实例）
        const self = this;

        return new Proxy(router, {
            get: (target, prop) => {
                if (prop === 'routeMessage') {
                    // 🔥 使用普通函数而非箭头函数，确保 self 指向正确的 Worker 实例
                    return async function(impulse: NeuralImpulse, targetQueue: string) {
                        // 🔥 标记子类已手动路由
                        self.hasManuallyRouted = true;
                        // 调用原始方法
                        return await target.routeMessage(impulse, targetQueue);
                    };
                }
                // 其他属性和方法直接返回
                return (target as any)[prop];
            }
        });
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
     * 🆕 辅助方法：路由消息并标记为已完成（防止二次路由）
     *
     * 使用场景：当子类手动调用 router.routeMessage() 后，需要调用此方法来标记已完成路由
     * 避免基类的 processImpulse() 方法再次路由消息，形成死循环。
     *
     * @example
     * ```typescript
     * // ❌ 错误写法（会导致死循环）
     * await this.router.routeMessage(impulse, "Q_ERROR");
     *
     * // ✅ 正确写法
     * await this.routeAndDone(impulse, "Q_ERROR");
     * ```
     */
    protected async routeAndDone(impulse: NeuralImpulse, targetQueue: string): Promise<boolean> {
        const result = await this.router.routeMessage(impulse, targetQueue);

        // 🔥 关键：标记已完成路由，防止基类再次路由
        impulse.actionIntent = 'Done';

        return result;
    }

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
        const startMsg = `[Worker ${this.id}] 启动并在队列 ${this.inputQueue.queueId} 上监听...`;
        console.log(startMsg);
        globalThis.logRaw?.(startMsg);

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

        const stopMsg = `[Worker ${this.id}] 已停止。`;
        console.log(stopMsg);
        globalThis.logRaw?.(stopMsg);
    }

    /**
     * 处理单个消息
     */
    private async processImpulse(impulse: NeuralImpulse): Promise<void> {
        const startTime = Date.now();
        const context: HookContext = {
            workerId: this.id,
            queueId: this.inputQueue.queueId,
            timestamp: startTime
        };

        // 🔥 重置手动路由标志（每个新消息都需要重新检测）
        this.hasManuallyRouted = false;

        // 📊 消息流动日志：开始处理
        const processStartMsg = `⚙️  [PROCESS] ${impulse.sessionId} | ${this.id} 开始处理 | from: ${this.inputQueue.queueId}`;
        console.log(processStartMsg);
        globalThis.logRaw?.(processStartMsg);

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

            // 3. 🔥 调用子类的 process() 方法（模板方法模式）
            // 子类通过 process() 方法处理消息并手动路由
            // @ts-ignore - 子类实现 protected process() 方法
            if (typeof this.process === 'function') {
                // @ts-ignore
                await this.process(preResult);
            }

            // 子类 process() 方法中应该手动调用 router.routeMessage()
            // 如果子类没有手动路由，这里会继续执行默认路由逻辑
            let processedImpulse = preResult;

            // 4. Post Hooks 执行
            const postResult = await this.postHooks.executeHooks(processedImpulse, HookType.POST_PROCESS, context);
            if (!postResult) return; // 拦截

            processedImpulse = postResult;
            processedImpulse.status = MessageStatus.COMPLETED;

            // 5. 路由下一步（自动检测子类是否已手动路由）
            if (this.hasManuallyRouted) {
                // ✅ 子类已手动路由，跳过自动路由
                const elapsed = Date.now() - startTime;
                const manualRouteMsg = `🔀 [PROCESS] ${impulse.sessionId} | ${this.id} 处理完成 | 耗时: ${elapsed}ms | 子类已手动路由，跳过自动路由`;
                console.log(manualRouteMsg);
                globalThis.logRaw?.(manualRouteMsg);
            } else {
                // 子类未手动路由，使用基类的默认路由逻辑
                const targetQueue = processedImpulse.actionIntent;
                if (targetQueue && targetQueue !== 'Done' && targetQueue !== 'Q_DONE') {
                    processedImpulse.updateSource(this.id);
                    const elapsed = Date.now() - startTime;
                    const completeMsg = `✅ [PROCESS] ${impulse.sessionId} | ${this.id} 处理完成 | 耗时: ${elapsed}ms | next: ${targetQueue}`;
                    console.log(completeMsg);
                    globalThis.logRaw?.(completeMsg);
                    await this.router.routeMessage(processedImpulse, targetQueue);
                } else {
                    const elapsed = Date.now() - startTime;
                    const finishMsg = `🏁 [PROCESS] ${impulse.sessionId} | ${this.id} 处理完成 | 耗时: ${elapsed}ms | 流程结束`;
                    console.log(finishMsg);
                    globalThis.logRaw?.(finishMsg);
                }
            }

        } catch (err: any) {
            impulse.status = MessageStatus.FAILED;
            this.internalErrorCount++;
            const elapsed = Date.now() - startTime;
            console.error(`❌ [PROCESS] ${impulse.sessionId} | ${this.id} 处理失败 | 耗时: ${elapsed}ms | error: ${err.message}`);

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
