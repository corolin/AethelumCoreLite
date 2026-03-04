import { NeuralImpulse } from '../core/message.js';
import type { AsyncAxonWorker } from '../core/worker.js';

export enum HookType {
    PRE_PROCESS = 'pre_process',
    POST_PROCESS = 'post_process',
    ERROR_HANDLER = 'error_handler',
    TRANSFORM = 'transform',
    FILTER = 'filter'
}

export enum HookExecutionStatus {
    SUCCESS = 'success',
    FAILED = 'failed',
    SKIPPED = 'skipped',
    TIMEOUT = 'timeout'
}

export interface HookContext {
    workerId: string;
    queueId: string;
    timestamp: number;
    [key: string]: any;
}

export interface AsyncHook {
    name: string;
    hookType: HookType;
    priority: number;
    enabled: boolean;
    timeoutMs: number;

    executeAsync(impulse: NeuralImpulse, context: HookContext): Promise<NeuralImpulse | null>;
    enable(): void;
    disable(): void;
}
