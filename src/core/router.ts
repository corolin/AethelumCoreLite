import { AsyncSynapticQueue } from './queue.js';
import { AsyncAxonWorker } from './worker.js';
import { NeuralImpulse, MessageStatus } from './message.js';
import { AsyncWorkerMonitor } from './monitor.js';
import { AsyncErrorHandler } from './error_handler.js';
import { getStructuredLogger } from '../utils/structured_logger.js';
import { ConfigurableQueueFactory, type QueueDefinition } from './queue-factory.js';
import type { HookPluginRegistry } from '../hooks/runtime.js';

import type { DynamicQueueStrategy } from '../config/runtime-schema.js';

const routerLogger = getStructuredLogger('CoreLiteRouter');

/**
 * 消息守恒对账报告（生命周期记账）：
 * `created` 应等于 `finished + errored + sunk + inFlight`，
 * `suspicious` 为疑似被管道吞没的脉冲数。
 */
export interface ConservationReport {
    /** 曾入队的唯一脉冲数 */
    created: number;
    /** 已登记完成（Q_FINISH） */
    finished: number;
    /** 已登记错误（Q_ERROR） */
    errored: number;
    /** 已登记销毁（Q_SINK） */
    sunk: number;
    /** 在途未终结 */
    inFlight: number;
    /** 在途超过阈值（suspiciousIdleMs）未终结——疑似被吞 */
    suspicious: number;
    /** created === finished + errored + sunk + inFlight */
    balanced: boolean;
}

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
    /** 可选插件注册表：提供后 ensureQueue 可按定义挂 hookPlugins（如 WAL） */
    private hookRegistry?: HookPluginRegistry | undefined;
    private dynamicQueueStrategy?: DynamicQueueStrategy | undefined;
    public monitor: AsyncWorkerMonitor;
    public errorHandler: AsyncErrorHandler;

    // ==== 消息守恒（生命周期记账） ====
    /** 在途脉冲：messageId → 最后出现位置（用于定位“被吞”的消息） */
    private pendingMessages = new Map<string, { lastQueue: string; lastTs: number }>();
    /** 生命周期计数器：入流量 vs 归宿登记 */
    private lifecycleCounters = { created: 0, finished: 0, errored: 0, sunk: 0 };
    /** 疑似丢失判定阈值（ms，见 getConservationReport / markSuspicious） */
    public suspiciousIdleMs: number = 60_000;

    constructor(options: boolean | {
        enableWal?: boolean;
        builtInQueues?: QueueDefinition[];
        skipBuiltInQueues?: boolean;
        hookRegistry?: HookPluginRegistry | undefined;
        dynamicQueues?: DynamicQueueStrategy | undefined;
    } = true) {
        const normalized = typeof options === 'boolean'
            ? { enableWal: options }
            : options;

        this.enableWal = normalized.enableWal ?? true;
        this.hookRegistry = normalized.hookRegistry;
        this.dynamicQueueStrategy = normalized.dynamicQueues;
        if (!normalized.skipBuiltInQueues) {
            this.setupBuiltinQueues(normalized.builtInQueues);
        }
        this.monitor = new AsyncWorkerMonitor();
        this.errorHandler = new AsyncErrorHandler(this);
    }

    /**
     * 注册系统内置强制队列
     *
     * @deprecated 内置的 Q_AUDIT_* 审查流水线自本版本起废弃：审查机制交由 Agent 层实现，
     * 框架不再关心内容审查。保留仅为兼容旧版，后续版本将移除。
     * Q_RESPONSE_SINK 为终端队列，不需要 WAL（其业务语义将随审查流程一并废弃，
     * 由新生命周期登记队列 Q_SINK 取代）。
     *
     * 生命周期登记队列（非废弃）：Q_FINISH（完成登记）、Q_SINK（销毁登记）、Q_ERROR（错误登记），
     * 是消息守恒审计的“归宿寄存器”，由框架自动写入，Agent 可挂记账 Worker 消费。
     */
    private setupBuiltinQueues(builtInQueues?: QueueDefinition[]): void {
        const definitions = builtInQueues ?? this.getDefaultBuiltInQueueDefinitions();
        for (const definition of definitions) {
            const isLifecycleSink = definition.id === 'Q_FINISH' || definition.id === 'Q_SINK';
            const autoExpand = isLifecycleSink ? false : (definition.autoExpand ?? true);
            const evictOldestOnFull = isLifecycleSink ? true : (definition.evictOldestOnFull ?? false);
            const capacity = isLifecycleSink && (!definition.capacity || definition.capacity <= 0)
                ? 10_000
                : (definition.capacity ?? 0);

            const queue = new AsyncSynapticQueue(
                definition.id,
                capacity,
                autoExpand,
                definition.shrinkIntervalMs ?? 10 * 60 * 1000,
                evictOldestOnFull,
            );
            this.registerQueue(queue);
        }
    }

    private getDefaultBuiltInQueueDefinitions(): QueueDefinition[] {
        // @deprecated Q_AUDIT_INPUT（AUDIT_I）、Q_AUDITED_INPUT（AUDIT_II）、Q_AUDIT_OUTPUT、Q_REFLECTION
        // 为原审查流水线的内置队列，自本版本起废弃；审查机制交由 Agent 层处理，框架不再关心。
        // 保留仅为兼容旧版，后续版本将移除。
        const durableQueues = [
            'Q_AUDIT_INPUT',
            'Q_AUDITED_INPUT',
            'Q_AUDIT_OUTPUT',
            'Q_ERROR',
            'Q_REFLECTION',
        ];

        const definitions: QueueDefinition[] = durableQueues.map((id) => ({
            id,
            capacity: 1000,
            autoExpand: true,
        }));
        definitions.push({
            id: 'Q_DONE',
            capacity: 1000,
            autoExpand: false,
        });
        definitions.push({
            id: 'Q_RESPONSE_SINK',
            capacity: 1000,
            autoExpand: false,
        });
        // 生命周期登记队列：消息归宿寄存器（守恒审计用），环形缓冲淘汰，杜绝无界堆积
        definitions.push({
            id: 'Q_FINISH',
            capacity: 10_000,
            autoExpand: false,
            evictOldestOnFull: true,
        });
        definitions.push({
            id: 'Q_SINK',
            capacity: 10_000,
            autoExpand: false,
            evictOldestOnFull: true,
        });

        return definitions;
    }

    /**
     * 手动注册队列（供不需要绑定 Worker 的独立消费端使用）
     */
    public registerQueue(queue: AsyncSynapticQueue): void {
        if (!this.queues.has(queue.queueId)) {
            this.queues.set(queue.queueId, queue);
        }
        // 注入丢弃归宿登记：队列丢弃消息（过期/拦截）时通知 Router 登记 Q_SINK
        // 🚨 终点登记队列（Q_SINK, Q_FINISH）自身丢弃时绝对不绑定 lifecycleSink，阻断自环与递归溢出
        if (queue.queueId !== 'Q_SINK' && queue.queueId !== 'Q_FINISH') {
            queue.onDiscard = (impulse, reason) => this.lifecycleSink(impulse, reason);
        }
    }

    /**
     * 运行时官方建队路径（v1.1.1 F1：动态 durable 队列）。
     *
     * 幂等：队列已存在时直接返回既有实例（契合 Q_DISPATCH:{id} 等按需复用语义）。
     * 不存在时按定义创建：
     *   - 构造时注入了 hookRegistry → 按 definition.hookPlugins 挂插件（如 `{ plugin: 'wal' }`）
     *   - 以 registerQueue 语义注册 → 注入 onDiscard（丢弃归宿登记）+ 纳入守恒对账
     *
     * 用法：`await router.ensureQueue({ id: 'Q_DISPATCH:x', capacity: 50, hookPlugins: [{ plugin: 'wal' }] })`
     */
    public async ensureQueue(definition: QueueDefinition): Promise<AsyncSynapticQueue> {
        const existing = this.queues.get(definition.id);
        if (existing) return existing;

        const factory = new ConfigurableQueueFactory(this.hookRegistry);
        const queue = await factory.createQueue(definition);
        this.registerQueue(queue);
        return queue;
    }

    /**
     * 注册新的工作器
     */
    public registerWorker(worker: AsyncAxonWorker): void {
        const queueId = worker.getInputQueue().queueId;
        if (!this.queues.has(queueId)) {
            // v1.1.1 F1: 与 registerQueue 同语义（注入 onDiscard 丢弃归宿登记），不再裸 set
            this.registerQueue(worker.getInputQueue());
        }

        this.workers.set(worker.id, worker);
        this.monitor.registerWorker(worker);

        if (this.isActive) {
            worker.start(); // 后台启动事件循环
        }
    }

    /**
     * 注销并移除工作器（不改变其运行状态，需调用者先 stop）
     */
    public unregisterWorker(workerId: string): void {
        this.workers.delete(workerId);
        this.monitor.unregisterWorker(workerId);
    }

    /**
     * 注销并移除队列
     */
    public unregisterQueue(queueId: string): void {
        const queue = this.queues.get(queueId);
        if (queue) {
            queue.close();
            this.queues.delete(queueId);
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
     * 停止顺序：monitor → close queues（唤醒 consumer）→ workers → queues.stop()（flush WAL）
     */
    public async stop(): Promise<void> {
        this.isActive = false;

        // 停止监控守护程序
        this.monitor.stop();

        // 先 close 所有队列，让阻塞在 asyncGet 上的 Worker/Platform 立即被唤醒
        for (const q of this.queues.values()) {
            q.close();
        }

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
     * 生命周期登记：脉冲处理完成（归宿 Q_FINISH）。
     * 由 Worker 基类在处理流程结束时自动调用；Agent 亦可显式标记。
     * 登记同时更新守恒计数并从在途追踪中移除。
     */
    public async lifecycleFinish(impulse: NeuralImpulse): Promise<boolean> {
        impulse.status = MessageStatus.COMPLETED;
        impulse.markHop('lifecycle:finish');
        return this.routeMessage(impulse, 'Q_FINISH');
    }

    /**
     * 生命周期登记：脉冲被销毁/丢弃（归宿 Q_SINK）。
     * 适用：钩子拦截、过期丢弃、明确作废等“不再继续流转”的脉冲。
     */
    public async lifecycleSink(impulse: NeuralImpulse, reason?: string): Promise<boolean> {
        impulse.status = MessageStatus.CANCELLED;
        if (reason) impulse.metadata['sink_reason'] = reason;
        impulse.markHop('lifecycle:sink');
        return this.routeMessage(impulse, 'Q_SINK');
    }

    /**
     * 消息守恒对账报告：
     * `created`（曾入队脉冲数）应与 `finished + errored + sunk + inFlight` 守恒；
     * `suspicious` 为在途超过 `suspiciousIdleMs` 未终结的脉冲数——即可能被某管道“吞没”的消息。
     * 详见 {@link getSuspiciousMessages} 按 messageId 回溯定位。
     */
    public getConservationReport(): ConservationReport {
        const { created, finished, errored, sunk } = this.lifecycleCounters;
        const inFlight = this.pendingMessages.size;
        const suspicious = this.countSuspicious();
        return {
            created,
            finished,
            errored,
            sunk,
            inFlight,
            suspicious,
            balanced: created === finished + errored + sunk + inFlight,
        };
    }

    /**
     * 疑似被吞消息明细：最后停留队列 + 闲置时长，供“哪个神经管道吞了消息”排查。
     */
    public getSuspiciousMessages(): Array<{ messageId: string; lastQueue: string; lastTs: number; idleMs: number }> {
        const now = Date.now();
        const out: Array<{ messageId: string; lastQueue: string; lastTs: number; idleMs: number }> = [];
        for (const [messageId, entry] of this.pendingMessages) {
            const idleMs = now - entry.lastTs;
            if (idleMs > this.suspiciousIdleMs) {
                out.push({ messageId, lastQueue: entry.lastQueue, lastTs: entry.lastTs, idleMs });
            }
        }
        return out;
    }

    private countSuspicious(): number {
        const now = Date.now();
        let n = 0;
        for (const entry of this.pendingMessages.values()) {
            if (now - entry.lastTs > this.suspiciousIdleMs) n++;
        }
        return n;
    }

    /**
     * 外部注入脉冲入口
     *
     * @deprecated 本方法强制将脉冲路由到已废弃的审查队列 Q_AUDIT_INPUT。
     * 审查机制交由 Agent 层实现后，外部输入应直接通过 `routeMessage` 路由到
     * Agent 自定义的入口队列（如 Q_QQ_GATEWAY_INGRESS）。
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

        // 📊 消息守恒标记
        impulse.markHop(`${targetQueueId}:route`);

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

        // @deprecated SINK 终点保护机制属原审查流水线（仅允许审计输出写入 SINK），随审查流程废弃。
        // 审查机制交由 Agent 层处理；Q_RESPONSE_SINK 将重新定位为生命周期记账队列 Q_SINK（销毁登记处）。
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

        // @deprecated 以下 AuditInputWorker 特殊路由逻辑属原审查流水线，随审查流程废弃。
        // 审查机制交由 Agent 层实现后，此类业务拓扑由 Agent 自行定义，框架不再内置。
        // 处理内部特殊路由逻辑：Audit Input 完毕应该去 BIZ
        if (impulse.sourceAgent === 'AuditInputWorker') {
            if (targetQueueId === 'Q_AUDIT_OUTPUT') {
                targetQueueId = 'Q_AUDITED_INPUT';
                impulse.actionIntent = targetQueueId;
            }
        }

        const isLifecycleQueue =
            targetQueueId === 'Q_FINISH' || targetQueueId === 'Q_SINK' || targetQueueId === 'Q_ERROR';
        if (!isLifecycleQueue) {
            impulse.status = MessageStatus.QUEUED;
        }

        let queue = this.queues.get(targetQueueId);
        if (!queue) {
            // 策略检查：若配置了 deny 策略且未匹配允许白名单，拒绝动态创建
            if (this.dynamicQueueStrategy?.mode === 'deny') {
                const allowed = this.dynamicQueueStrategy.allowPatterns?.some(pattern => {
                    if (pattern.endsWith('*')) return targetQueueId.startsWith(pattern.slice(0, -1));
                    return targetQueueId === pattern;
                });
                if (!allowed) {
                    emitRouterLog('warning', `[Router] 动态建队策略拒绝建队: ${targetQueueId} (mode=deny)`, {
                        event: 'router.dynamic_queue_denied',
                        targetQueueId,
                        sessionId: impulse.sessionId,
                    });
                    if (!isLifecycleQueue) {
                        await this.lifecycleSink(impulse, 'dynamic_queue_denied');
                    }
                    return false;
                }
            }

            // 动态创建队列
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
            const isLifecycleSink = targetQueueId === 'Q_FINISH' || targetQueueId === 'Q_SINK';
            const defaultCapacity = isLifecycleSink ? 10_000 : (this.dynamicQueueStrategy?.defaultCapacity ?? 1000);
            const defaultAutoExpand = isLifecycleSink ? false : (this.dynamicQueueStrategy?.defaultAutoExpand ?? true);
            const evictOldestOnFull = isLifecycleSink ? true : false;
            const defaultShrinkMs = this.dynamicQueueStrategy?.defaultShrinkIntervalMs ?? 10 * 60 * 1000;
            queue = new AsyncSynapticQueue(targetQueueId, defaultCapacity, defaultAutoExpand, defaultShrinkMs, evictOldestOnFull);
            this.registerQueue(queue);
        }

        // 入目标队列前先快照“上一跳来源队列”信息。
        const prevSrcQueueId = impulse.metadata['_src_queue_id'] as string | undefined;
        const prevSrcLsn = impulse.metadata['_src_wal_lsn'] as number | undefined;

        let discarded = false;
        const result = await queue.asyncPut(impulse, () => { discarded = true; });

        if (discarded && queue.onDiscard) return result; // onDiscard 已接管终点登记

        if (result) {
            // 📊 守恒精确记账：仅在实际入队成功时计入在途与生命周期
            if (isLifecycleQueue) {
                if (!this.pendingMessages.has(impulse.messageId)) this.lifecycleCounters.created++;
                if (targetQueueId === 'Q_FINISH') this.lifecycleCounters.finished++;
                else if (targetQueueId === 'Q_SINK') this.lifecycleCounters.sunk++;
                else this.lifecycleCounters.errored++;
                this.pendingMessages.delete(impulse.messageId);
            } else {
                if (!this.pendingMessages.has(impulse.messageId)) this.lifecycleCounters.created++;
                this.pendingMessages.set(impulse.messageId, { lastQueue: targetQueueId, lastTs: Date.now() });
            }

            // 移交成功：对来源队列 confirmDelivery（WAL tombstone）
            if (prevSrcQueueId) {
                const srcQueue = this.queues.get(prevSrcQueueId);
                if (srcQueue) {
                    await srcQueue.confirmDelivery(impulse, prevSrcLsn);
                }
                
                // 标记该 LSN 已被路由器安全处理并确认移交，Worker.finally 无需兜底清除
                if (prevSrcLsn !== undefined) {
                    impulse.metadata['_wal_handled_for_lsn'] = prevSrcLsn;
                }

                // 仅清理旧标记；若目标队列已写入新的 _src_*（用于下一跳），不能误删。
                if (impulse.metadata['_src_queue_id'] === prevSrcQueueId) {
                    delete impulse.metadata['_src_queue_id'];
                }
                if (impulse.metadata['_src_wal_lsn'] === prevSrcLsn) {
                    delete impulse.metadata['_src_wal_lsn'];
                }
            }
        } else {
            // 入队失败处理
            emitRouterLog('warning', `[Router] 消息入队失败: ${targetQueueId} (队列已满或已关闭)`, {
                event: 'router.put_failed',
                targetQueueId,
                messageId: impulse.messageId,
                sessionId: impulse.sessionId,
            });
            if (!isLifecycleQueue) {
                // 业务队列入队失败：若在途则清理并登记销毁，防止成为永久悬挂在途
                if (this.pendingMessages.has(impulse.messageId)) {
                    await this.lifecycleSink(impulse, 'queue_put_failed');
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
