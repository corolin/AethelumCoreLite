import { NeuralImpulse } from '../core/message.js';
import type { AsyncAxonWorker } from '../core/worker.js';

export enum HookType {
    PRE_PROCESS = 'pre_process',
    POST_PROCESS = 'post_process',
    ERROR_HANDLER = 'error_handler',
    TRANSFORM = 'transform',
    FILTER = 'filter',
    // 队列钩子
    QUEUE_BEFORE_PUT = 'queue_before_put',
    QUEUE_AFTER_ACK = 'queue_after_ack'
}

/**
 * Hook 执行结果（写入 `NeuralImpulse.metadata['hook_execution_status']` 等，供监控与扩展使用）
 */
export enum HookExecutionStatus {
    SUCCESS = 'success',
    FAILED = 'failed',
    SKIPPED = 'skipped',
    TIMEOUT = 'timeout'
}

export interface HookContext {
    workerId?: string;
    queueId: string;
    timestamp: number;
    error?: unknown;
    stage?: string;
    /**
     * 中止信号，由 HookChain 在超时时触发。
     * Hook 实现应检查此信号以提前终止外部 I/O 操作（fetch、文件读写等），
     * 避免超时后仍产生副作用或资源泄漏。
     */
    signal?: AbortSignal;
    /**
     * 发射旁路脉冲到指定队列（fan-out）。
     * 由执行方注入：Worker 上下文注入 Router 路由能力，
     * 供 Hook 在处理过程中向管道注入独立脉冲（如演绎结束 → 旁路到 Live2D Egress）。
     * Hook 可自行决定是否 await；不 await 即不阻塞主通路流转。
     */
    emit?: (impulse: NeuralImpulse, targetQueueId: string) => Promise<boolean>;
    [key: string]: unknown;
}

export interface AsyncHook {
    name: string;
    hookType: HookType;
    priority: number;
    enabled: boolean;
    timeoutMs: number;
    /**
     * 尽力而为：为 true 时执行失败/超时仅告警并继续链，不中断消息流转。
     * 适合生命周期登记、记忆写入、遥测等旁路副作用。
     */
    bestEffort: boolean;

    executeAsync(impulse: NeuralImpulse, context: HookContext): Promise<NeuralImpulse | null>;
    enable(): void;
    disable(): void;
}
