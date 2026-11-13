import { AsyncSynapticQueue } from './queue.js';
import { NeuralImpulse, MessageStatus } from './message.js';
import { AsyncHookChain } from '../hooks/chain.js';
import { HookType } from '../hooks/types.js';
import type { HookContext } from '../hooks/types.js';
import {
    createWorkerPluginMount,
    disposeHookPluginDisposers,
    type HookPluginAttachResult,
    type HookPluginMount,
    type HookPluginRegistry,
    type HookPluginSpec,
} from '../hooks/runtime.js';
import { CoreLiteRouter } from './router.js';
import { getStructuredLogger } from '../utils/structured_logger.js';

/** Worker 层结构化日志（错误/告警/生命周期事件可聚合；流量日志保留 console 可读性） */
const workerLogger = getStructuredLogger('AsyncAxonWorker');

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

    /**
     * 集中的 SINK 安全校验（Router 和 Worker 共用）
     *
     * @deprecated 属原审查流水线（仅允许审计输出写入 Q_RESPONSE_SINK），随审查流程废弃。
     * 审查机制交由 Agent 层处理；Q_RESPONSE_SINK 将重新定位为生命周期记账队列 Q_SINK（销毁登记处），
     * 届时不再需要“审计出口白名单”语义。
     */
    public static readonly ALLOWED_SINK_SOURCES = new Set(['Q_AUDIT_OUTPUT', 'AuditOutputWorker']);

    /**
     * @deprecated 属原审查流水线的 SINK 白名单校验，随审查流程废弃，见 {@link ALLOWED_SINK_SOURCES}。
     */
    public static isSinkAccessAllowed(source: string): boolean {
        return AsyncAxonWorker.ALLOWED_SINK_SOURCES.has(source);
    }

    private inputQueue: AsyncSynapticQueue;
    private router: CoreLiteRouter;

    private preHooks: AsyncHookChain;
    private postHooks: AsyncHookChain;
    private errorHooks: AsyncHookChain;

    private stopRequested: boolean = false;
    private _isProcessing: boolean = false;

    // runLoop 代际计数器，防止恢复时启动重复循环
    private runLoopGeneration: number = 0;
    // 保存当前 runLoop Promise，供 stop() 等待其自然退出
    private runLoopPromise: Promise<void> | null = null;

    // ==== 监控与恢复专用指标 ====
    private internalErrorCount: number = 0;
    private lastActiveTimestamp: number = Date.now();
    private processedCount: number = 0;
    
    // 心跳与任务追踪（解决假死误判）
    public processingStartTime: number = 0;
    public lastHeartbeatTime: number = Date.now();

    private originalRouter: CoreLiteRouter;
    private pluginDisposers: Array<() => void | Promise<void>> = [];

    // ==== 观察者信号 ====
    // state 变为 RUNNING 时 resolve，用于替换 PAUSED/ERROR 的轮询等待
    private _stateSignal: { promise: Promise<void>; resolve: () => void } | null = null;
    // isProcessing 变为 false 时 resolve，用于替换 stop() 的轮询等待
    private _processingSignal: { promise: Promise<void>; resolve: () => void } | null = null;

    // state 内部存储
    private _state: WorkerState = WorkerState.INITIALIZING;

    constructor(id: string, inputQueue: AsyncSynapticQueue, router: CoreLiteRouter) {
        this.id = id;
        this.inputQueue = inputQueue;
        this.originalRouter = router;

        // 🔥 创建代理 Router，自动检测子类的路由调用
        this.router = this._createProxiedRouter(router);

        this.preHooks = new AsyncHookChain(`${id}_pre`);
        this.postHooks = new AsyncHookChain(`${id}_post`);
        this.errorHooks = new AsyncHookChain(`${id}_error`);
    }

    // ==== state getter/setter（观察者：state → RUNNING 时唤醒等待中的 runLoop） ====

    public get state(): WorkerState {
        return this._state;
    }

    public set state(newState: WorkerState) {
        this._state = newState;
        // 当状态恢复为 RUNNING 时，唤醒在 PAUSED/ERROR 中等待的 runLoop
        if (newState === WorkerState.RUNNING && this._stateSignal) {
            const sig = this._stateSignal;
            this._stateSignal = null;
            sig.resolve();
        }
    }

    // ==== isProcessing getter/setter（观察者：false 时唤醒等待中的 stop()） ====

    private get isProcessing(): boolean {
        return this._isProcessing;
    }

    private set isProcessing(value: boolean) {
        this._isProcessing = value;
        if (!value && this._processingSignal) {
            const sig = this._processingSignal;
            this._processingSignal = null;
            sig.resolve();
        }
    }

    // ==== 信号辅助方法 ====

    private _createSignal(): { promise: Promise<void>; resolve: () => void } {
        let resolve!: () => void;
        const promise = new Promise<void>(r => { resolve = r; });
        return { promise, resolve };
    }

    /**
     * 在 PAUSED/ERROR 状态下等待，直到 state 变回 RUNNING 才继续
     */
    private async _waitForRunning(): Promise<void> {
        this._stateSignal = this._createSignal();
        await this._stateSignal.promise;
    }

    // ==== 运行中单脉冲局部追踪（防止跨 Worker 标记泄漏与并发串扰） ====
    private activeHandledImpulseId: string | null = null;
    private manualRouteResult: boolean | undefined;

    /**
     * 🔥 创建代理 Router，自动标记消息已被手动路由
     *
     * 当子类调用 this.router.routeMessage() 时，
     * 代理在 Worker 局部状态中标记当前脉冲已路由，让 processImpulse() 跳过自动路由。
     *
     * 注意：使用局部状态记录当前处理的脉冲，不再将 `_manually_routed` 写入消息元数据，
     * 避免元数据随零拷贝脉冲渗透到下游 Worker 导致下游终点登记被误跳过。
     */
    private _createProxiedRouter(router: CoreLiteRouter): CoreLiteRouter {
        const self = this;
        return new Proxy(router, {
            get: (target, prop) => {
                if (prop === 'routeMessage') {
                    return async function(impulse: NeuralImpulse, targetQueue: string) {
                        const result = await target.routeMessage(impulse, targetQueue);
                        if (self.activeHandledImpulseId === impulse.messageId) {
                            self.manualRouteResult = self.manualRouteResult || result;
                        }
                        // 防御性清理旧数据残留
                        if (impulse.metadata['_manually_routed']) {
                            delete impulse.metadata['_manually_routed'];
                        }
                        return result;
                    };
                }
                return (target as any)[prop];
            }
        });
    }

    public getPreHooks(): AsyncHookChain { return this.preHooks; }
    public getPostHooks(): AsyncHookChain { return this.postHooks; }
    public getErrorHooks(): AsyncHookChain { return this.errorHooks; }
    public getInputQueue(): AsyncSynapticQueue { return this.inputQueue; }

    public async attachHookPlugins(
        registry: HookPluginRegistry,
        specs: HookPluginSpec[],
        mount: Partial<HookPluginMount> = {},
    ): Promise<HookPluginAttachResult> {
        const result = await registry.resolve(createWorkerPluginMount(this, mount), specs);

        for (const hook of result.hooks) {
            if (hook.hookType === HookType.PRE_PROCESS) {
                this.preHooks.addHook(hook);
                continue;
            }
            if (hook.hookType === HookType.POST_PROCESS) {
                this.postHooks.addHook(hook);
                continue;
            }
            if (hook.hookType === HookType.ERROR_HANDLER) {
                this.errorHooks.addHook(hook);
            }
        }

        this.pluginDisposers.push(...result.disposers);
        return result;
    }

    // 暴露给 Monitor 采集的指标
    public getInternalErrorCount(): number { return this.internalErrorCount; }
    public getLastActiveTime(): number { return this.lastActiveTimestamp; }
    public getProcessedCount(): number { return this.processedCount; }
    public getIsProcessing(): boolean { return this.isProcessing; }

    /**
     * 供长耗时子类（如 LLM 输出流）调用的保活心跳
     */
    public heartbeat(): void {
        this.lastHeartbeatTime = Date.now();
    }

    /**
     * 供 Monitor 安全地设置 Worker 为错误状态（熔断隔离）
     */
    public setErrorState(): void {
        this.state = WorkerState.ERROR;
    }

    /**
     * 供 Monitor 在恢复时重置内部错误计数，避免无限熔断循环
     */
    public resetInternalErrorCount(): void {
        this.internalErrorCount = 0;
        this.lastActiveTimestamp = Date.now();
    }

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

        // 🔥 代理已在消息上设置 _manually_routed（防二次路由）；
        // 不再覆盖 actionIntent，保留“流程结束”语义给终结点使用。

        return result;
    }

    /**
     * 启动 Worker
     */
    public async start(): Promise<void> {
        if (this.state === WorkerState.RUNNING) return;

        this.state = WorkerState.RUNNING;
        this.stopRequested = false;
        this.runLoopGeneration++; // 使旧 runLoop 自行退出

        // 不再 await 这个调用，让它在后台循环
        this.runLoopPromise = this.runLoop(this.runLoopGeneration);
        this.runLoopPromise.catch(err => {
            workerLogger.error(`[Worker ${this.id}] 发生致命错误`, {
                metadata: { workerId: this.id, error: err instanceof Error ? err.message : String(err) },
            });
            console.error(`[Worker ${this.id}] 发生致命错误:`, err);
            this.state = WorkerState.ERROR;
        }).finally(() => {
            this.runLoopPromise = null;
        });
    }

    /**
     * 停止 Worker
     */
    public async stop(): Promise<void> {
        this.stopRequested = true;
        this.state = WorkerState.STOPPING;

        // 关闭输入队列，让 runLoop 中阻塞的 asyncGet 立即返回 null，
        // 从而快速检查到 stopRequested 并退出循环
        this.inputQueue.close();

        // 若当前正在处理消息，等待其完成（观察者信号，无需轮询）
        if (this.isProcessing) {
            this._processingSignal = this._createSignal();
            await Promise.race([
                this._processingSignal.promise,
                // 最长兜底等待 5s，防止子类处理卡死导致 stop() 永久挂起
                new Promise<void>(r => setTimeout(r, 5000)),
            ]);
            this._processingSignal = null;
        }

        // 等待 runLoop 自然退出（最多 3s 兜底），确保收尾逻辑完成
        if (this.runLoopPromise) {
            await Promise.race([
                this.runLoopPromise.catch(() => {}),
                new Promise<void>(r => setTimeout(r, 3000)),
            ]);
        }

        this.state = WorkerState.STOPPED;
        await disposeHookPluginDisposers(this.pluginDisposers);
    }

    /**
     * Worker 主循环 - 基于 Node.js 事件循环的自然异步等待
     */
    private async runLoop(expectedGeneration: number): Promise<void> {
        const startMsg = `[Worker ${this.id}] 启动并在队列 ${this.inputQueue.queueId} 上监听...`;
        console.log(startMsg);
        globalThis.logRaw?.(startMsg);

        while (!this.stopRequested && this.runLoopGeneration === expectedGeneration) {
            try {
                if (this.state === WorkerState.PAUSED || this.state === WorkerState.ERROR) {
                    // 观察者等待：直到外部将 state 改回 RUNNING 才继续（无需轮询）
                    await this._waitForRunning();
                    continue;
                }

                // 天然异步等待，不阻塞 Node.js 其他事件循环任务
                // 设置一个超时，以便可以响应 stopRequested
                const impulse = await this.inputQueue.asyncGet(1000);

                // 刷新活跃心跳
                this.lastActiveTimestamp = Date.now();

                if (!impulse) {
                    // 队列已关闭时立即退出，避免 asyncGet 持续返回 null 导致忙循环饿死事件循环
                    if (this.inputQueue.isClosed()) break;
                    continue; // 仅超时，继续等待
                }

                this.isProcessing = true;
                await this.processImpulse(impulse);
                this.processedCount++;
                this.isProcessing = false;

            } catch (err) {
                this.internalErrorCount++;
                workerLogger.error(`[Worker ${this.id}] 处理循环异常`, {
                    metadata: { workerId: this.id, error: err instanceof Error ? err.message : String(err) },
                });
                console.error(`[Worker ${this.id}] 处理循环异常:`, err);
                // 短暂延迟防止死循环吃满 CPU
                await new Promise(resolve => setTimeout(resolve, 1000));
            } finally {
                this.isProcessing = false;
            }
        }

        // 只有当前代的循环才打印停止消息
        if (this.runLoopGeneration === expectedGeneration) {
            const stopMsg = `[Worker ${this.id}] 已停止。`;
            console.log(stopMsg);
            globalThis.logRaw?.(stopMsg);
        }
    }

    /**
     * 处理单个消息
     */
    private async processImpulse(impulse: NeuralImpulse): Promise<void> {
        const startTime = Date.now();
        const context: HookContext = {
            workerId: this.id,
            queueId: this.inputQueue.queueId,
            timestamp: startTime,
            // 旁路发射能力：Hook 可在处理过程中向管道注入独立脉冲（fan-out），
            // 使用原始 Router 避免代理改写目标脉冲的 actionIntent。
            emit: (targetImpulse, targetQueueId) => this.originalRouter.routeMessage(targetImpulse, targetQueueId),
        };

        // 🔥 局部追踪当前处理的消息 ID
        this.activeHandledImpulseId = impulse.messageId;
        this.manualRouteResult = undefined;
        delete impulse.metadata['_manually_routed']; // 清理历史残留

        let isSettled = false;

        // 🔥 更新长时任务监控启动参数
        this.processingStartTime = startTime;
        this.heartbeat();
        impulse.markHop(`${this.id}:process`);

        // 🔥 快照当前来源 WAL 参数，用于 finally 中的兜底清理
        const prevSrcQueueId = impulse.metadata['_src_queue_id'] as string | undefined;
        const prevSrcWalLsn = impulse.metadata['_src_wal_lsn'] as number | undefined;

        // 📊 消息流动日志：开始处理
        const processStartMsg = `⚙️  [PROCESS] ${impulse.sessionId} | ${this.id} 开始处理 | from: ${this.inputQueue.queueId}`;
        console.log(processStartMsg);
        globalThis.logRaw?.(processStartMsg);

        try {
            impulse.status = MessageStatus.PROCESSING;

            // 1. SINK 安全校验（@deprecated 属原审查流水线，见 validateSinkSecurity）
            if (!this.validateSinkSecurity(impulse)) {
                impulse.actionIntent = 'Q_ERROR';
                impulse.metadata['error_message'] = 'SINK_SECURITY_VIOLATION';
                isSettled = await this.originalRouter.routeMessage(impulse, 'Q_ERROR');
                return;
            }

            // 2. Pre Hooks 执行
            const preResult = await this.preHooks.executeHooks(impulse, HookType.PRE_PROCESS, context);
            if (!preResult) {
                // 拦截：登记销毁
                isSettled = await this.router.lifecycleSink(impulse, 'pre_hook_intercepted');
                return;
            }

            // 3. 调用子类的 process() 方法（模板方法模式）
            // 子类通过 process() 方法处理消息并手动路由
            await this.process(preResult);

            let processedImpulse = preResult;

            // 4. Post Hooks 执行
            const postResult = await this.postHooks.executeHooks(processedImpulse, HookType.POST_PROCESS, context);
            if (!postResult) {
                // 拦截：登记销毁
                isSettled = await this.router.lifecycleSink(processedImpulse, 'post_hook_intercepted');
                return;
            }

            processedImpulse = postResult;

            // 5. 路由下一步（通过 Worker 局部状态检查当前脉冲是否已被子类/代理手动路由）
            if (this.manualRouteResult !== undefined) {
                // ✅ 消息已被手动路由（routeAndDone 或代理已标记），跳过自动路由
                // 状态由手动路由时确定，不再在移交后覆写已投递脉冲的状态
                isSettled = this.manualRouteResult;
                const elapsed = Date.now() - startTime;
                const manualRouteMsg = `🔀 [PROCESS] ${impulse.sessionId} | ${this.id} 处理完成 | 耗时: ${elapsed}ms | 子类已手动路由，跳过自动路由`;
                console.log(manualRouteMsg);
                globalThis.logRaw?.(manualRouteMsg);
                impulse.markHop(`${this.id}:done`);
            } else {
                // 子类未手动路由，使用基类的默认路由逻辑
                const targetQueue = processedImpulse.actionIntent;
                if (targetQueue && targetQueue !== 'Done' && targetQueue !== 'Q_DONE') {
                    if (targetQueue === this.inputQueue.queueId) {
                        // 🔥 缺陷 B 修复：目标队列是当前 Worker 自身的输入队列！
                        // 阻断自环并登记为流程结束
                        workerLogger.warning(`[Worker ${this.id}] 检测到未修改的 actionIntent 指向自身输入队列 (${targetQueue})，已阻断自环并终结流程`, {
                            metadata: { workerId: this.id, sessionId: impulse.sessionId, messageId: impulse.messageId },
                        });
                        impulse.markHop(`${this.id}:done`);
                        processedImpulse.status = MessageStatus.COMPLETED;
                        isSettled = await this.router.lifecycleFinish(processedImpulse);
                    } else {
                        processedImpulse.updateSource(this.id);
                        const elapsed = Date.now() - startTime;
                        const completeMsg = `✅ [PROCESS] ${impulse.sessionId} | ${this.id} 处理完成 | 耗时: ${elapsed}ms | next: ${targetQueue}`;
                        console.log(completeMsg);
                        globalThis.logRaw?.(completeMsg);
                        impulse.markHop(`${this.id}:done`);
                        processedImpulse.status = MessageStatus.COMPLETED;
                        isSettled = await this.originalRouter.routeMessage(processedImpulse, targetQueue);
                    }
                } else {
                    // 🏁 流程结束：自动登记完成（消息归宿 Q_FINISH，守恒审计）
                    const elapsed = Date.now() - startTime;
                    const finishMsg = `🏁 [PROCESS] ${impulse.sessionId} | ${this.id} 处理完成 | 耗时: ${elapsed}ms | 流程结束`;
                    console.log(finishMsg);
                    globalThis.logRaw?.(finishMsg);
                    impulse.markHop(`${this.id}:done`);
                    processedImpulse.status = MessageStatus.COMPLETED;
                    isSettled = await this.router.lifecycleFinish(processedImpulse);
                }
            }

        } catch (err: any) {
            impulse.status = MessageStatus.FAILED;
            this.internalErrorCount++;
            const elapsed = Date.now() - startTime;
            console.error(`❌ [PROCESS] ${impulse.sessionId} | ${this.id} 处理失败 | 耗时: ${elapsed}ms | error: ${err.message}`);
            impulse.markHop(`${this.id}:error`);

            const errorContext = {
                ...context,
                error: err,
                stage: 'execute_process'
            };

            isSettled = await this.router.errorHandler.handleError(err as Error, impulse, errorContext);

            try {
                // 执行 Error Hooks
                const errorResult = await this.errorHooks.executeHooks(impulse, HookType.ERROR_HANDLER, errorContext);
                // 🔥 缺陷 A 修复：只有当 ErrorHook 明确转道（非 Q_ERROR、非自身队列且非原未修改意图）时才允许重路由
                if (
                    errorResult &&
                    errorResult.actionIntent !== 'Q_ERROR' &&
                    errorResult.actionIntent !== this.inputQueue.queueId &&
                    errorResult.actionIntent !== impulse.actionIntent
                ) {
                    const retries = Number(errorResult.metadata['_error_retries'] ?? 0);
                    if (retries >= 3) {
                        workerLogger.warning(`[Worker ${this.id}] 错误钩子重试次数超限 (${retries})，已转入销毁登记`, {
                            metadata: { workerId: this.id, messageId: errorResult.messageId },
                        });
                        await this.router.lifecycleSink(errorResult, 'max_error_retries_exceeded');
                    } else {
                        errorResult.metadata['_error_retries'] = retries + 1;
                        await this.originalRouter.routeMessage(errorResult, errorResult.actionIntent);
                    }
                }
            } catch (fatalErr) {
                console.error(`[Worker ${this.id}] ErrorHook 也发生致命错误:`, fatalErr);
            }
        } finally {
            // 下游确认成功后才清理来源 WAL。停机或投递失败时保留原记录供重放。
            if (isSettled && prevSrcQueueId === this.inputQueue.queueId && prevSrcWalLsn !== undefined) {
                if (impulse.metadata['_wal_handled_for_lsn'] !== prevSrcWalLsn) {
                    await this.inputQueue.confirmDelivery(impulse, prevSrcWalLsn);
                }
                // 清理本次 handled 标记，避免污染下个 Worker 的处理
                if (impulse.metadata['_wal_handled_for_lsn'] === prevSrcWalLsn) {
                    delete impulse.metadata['_wal_handled_for_lsn'];
                }
            }

            // 重置运行中单脉冲局部追踪
            this.activeHandledImpulseId = null;
            this.manualRouteResult = undefined;
        }
    }

    /**
     * 严格的 SINK 安全校验 (使用集中化的校验逻辑)
     *
     * @deprecated 属原审查流水线，随审查流程废弃，见 {@link ALLOWED_SINK_SOURCES}。
     */
    private validateSinkSecurity(impulse: NeuralImpulse): boolean {
        if (impulse.actionIntent === 'Q_RESPONSE_SINK') {
            if (!AsyncAxonWorker.isSinkAccessAllowed(impulse.sourceAgent)) {
                console.warn(`[SECURITY VIOLATION] Worker ${this.id} 拒绝非法访问: ${impulse.sourceAgent} 试图绕过审计直达 Q_RESPONSE_SINK`);
                return false;
            }
        }
        return true;
    }

    /**
     * 子类应覆盖此方法实现具体的消息处理逻辑
     * 默认实现为空操作（基类将使用默认路由）
     */
    protected async process(_impulse: NeuralImpulse): Promise<void> {
        // 默认空操作，子类覆盖
    }
}
