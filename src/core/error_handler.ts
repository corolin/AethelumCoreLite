import { CoreLiteRouter } from './router.js';
import { NeuralImpulse, MessagePriority } from './message.js';

export enum AsyncErrorType {
    VALIDATION_ERROR = "validation_error",
    PROCESS_ERROR = "process_error",
    ROUTING_ERROR = "routing_error",
    TIMEOUT_ERROR = "timeout_error",
    RESOURCE_ERROR = "resource_error",
    SECURITY_ERROR = "security_error",
    HOOK_ERROR = "hook_error"
}

export interface ErrorContext {
    workerId?: string;
    queueId?: string;
    stage?: string;
    timestamp?: number;
    additionalInfo?: Record<string, any>;
}

export class AsyncErrorHandler {
    private router: CoreLiteRouter;
    private errorStats: Map<AsyncErrorType, number> = new Map();

    constructor(router: CoreLiteRouter) {
        this.router = router;

        for (const type of Object.values(AsyncErrorType)) {
            this.errorStats.set(type as AsyncErrorType, 0);
        }
    }

    /**
     * 处理错误
     * @param error 异常对象
     * @param impulse 原始神经脉冲
     * @param context 错误上下文
     * @returns boolean 是否处理/路由成功
     */
    public async handleError(error: Error, impulse: NeuralImpulse | null, context: ErrorContext): Promise<boolean> {
        // 保证时间戳和附属信息
        context.timestamp = context.timestamp || Date.now();
        context.additionalInfo = context.additionalInfo || {};

        // 分类错误
        const errorType = this.classifyError(error, context);

        // 更新统计 (在 Node.js 单线程模型中直接操作即可，不需要 Python 的 asyncio.Lock)
        const currentCount = this.errorStats.get(errorType) || 0;
        this.errorStats.set(errorType, currentCount + 1);

        // 记录错误
        console.error(
            `[ErrorHandler] 类型: ${errorType}, ` +
            `消息: ${error.message}, ` +
            `上下文: ${JSON.stringify(context)}`
        );

        // 创建错误脉冲
        const errorImpulse = this.createErrorImpulse(error, impulse, errorType, context);

        try {
            // Python 版是 Q_ERROR_HANDLER。我们将其路由到内建的 Q_ERROR 保持统一调度通道
            const success = await this.router.routeMessage(errorImpulse, 'Q_ERROR');
            if (!success) {
                console.warn(`[ErrorHandler] Q_ERROR 路由失败`);
                return false;
            }
            return true;
        } catch (e) {
            console.error(`[ErrorHandler] 无法路由错误脉冲:`, e);
            return false;
        }
    }

    private classifyError(error: Error, context: ErrorContext): AsyncErrorType {
        const errorMsg = (error.message || '').toLowerCase();
        const stage = (context.stage || '').toLowerCase();

        if (errorMsg.includes('validation') || errorMsg.includes('验证')) {
            return AsyncErrorType.VALIDATION_ERROR;
        } else if (errorMsg.includes('security') || errorMsg.includes('permission') || errorMsg.includes('权限')) {
            return AsyncErrorType.SECURITY_ERROR;
        } else if (stage.includes('routing') || stage.includes('路由')) {
            return AsyncErrorType.ROUTING_ERROR;
        } else if (stage.includes('hook') || stage === 'hook') {
            return AsyncErrorType.HOOK_ERROR;
        } else if (errorMsg.includes('timeout') || errorMsg.includes('超时')) {
            return AsyncErrorType.TIMEOUT_ERROR;
        } else if (errorMsg.includes('resource') || errorMsg.includes('资源')) {
            return AsyncErrorType.RESOURCE_ERROR;
        } else {
            return AsyncErrorType.PROCESS_ERROR;
        }
    }

    private createErrorImpulse(
        error: Error,
        originalImpulse: NeuralImpulse | null,
        errorType: AsyncErrorType,
        context: ErrorContext
    ): NeuralImpulse {
        const originalSessionId = originalImpulse?.sessionId || 'unknown';
        const originalSource = originalImpulse?.sourceAgent || 'unknown';

        const errorImpulse = new NeuralImpulse({
            sessionId: originalSessionId, // 继承导致错误的会话
            actionIntent: 'Q_ERROR',
            content: error.message,
            priority: MessagePriority.CRITICAL // 通常错误具有更高的优先级
        });

        errorImpulse.metadata = {
            error_type: errorType,
            error_message: error.message,
            error_stack: error.stack,
            original_session_id: originalSessionId,
            original_source: originalSource,
            error_context: {
                worker_id: context.workerId,
                queue_id: context.queueId,
                stage: context.stage,
                timestamp: context.timestamp
            },
            timestamp: Date.now()
        };

        return errorImpulse;
    }

    public getErrorStats(): Record<string, number> {
        const stats: Record<string, number> = {};
        for (const [type, count] of this.errorStats.entries()) {
            stats[type] = count;
        }
        return stats;
    }

    public resetStats(): void {
        for (const type of Object.values(AsyncErrorType)) {
            this.errorStats.set(type as AsyncErrorType, 0);
        }
        console.info("[ErrorHandler] 错误统计已重置");
    }
}
