import { NeuralImpulse, MessageStatus } from '../core/message.js';
import { HookType, HookExecutionStatus } from './types.js';
import type { AsyncHook, HookContext } from './types.js';

export class AsyncHookChain {
    private name: string;
    private hooks: AsyncHook[] = [];

    constructor(name: string) {
        this.name = name;
    }

    /**
     * 按优先级添加 Hook
     */
    public addHook(hook: AsyncHook): void {
        this.hooks.push(hook);
        // 按优先级降序排列
        this.hooks.sort((a, b) => b.priority - a.priority);
    }

    public removeHook(hookName: string): boolean {
        const initialLength = this.hooks.length;
        this.hooks = this.hooks.filter(h => h.name !== hookName);
        return this.hooks.length < initialLength;
    }

    public clear(): void {
        this.hooks = [];
    }

    public getHooksByType(type: HookType): AsyncHook[] {
        return this.hooks.filter(h => h.hookType === type && h.enabled);
    }

    /**
     * 执行特定类型的所有 Hooks
     * 
     * @param impulse 神经脉冲
     * @param hookType Hook类型 (Pre, Post, 等)
     * @param context Hook上下文
     * @returns 经过处理的 NeuralImpulse 或 null (若被Filter拦截)
     */
    public async executeHooks(
        impulse: NeuralImpulse,
        hookType: HookType,
        context: HookContext
    ): Promise<NeuralImpulse | null> {
        const hooksToRun = this.getHooksByType(hookType);
        if (hooksToRun.length === 0) return impulse;

        let currentImpulse: NeuralImpulse | null = impulse;

        for (const hook of hooksToRun) {
            if (!currentImpulse) break; // 若前面的 Hook 将脉冲置为 null，则终止链式调用

            try {
                let result: NeuralImpulse | null;

                if (hook.timeoutMs > 0) {
                    // 创建 AbortController，超时时触发 abort 通知 Hook 实现终止外部 I/O
                    const abortController = new AbortController();
                    const hookContext = { ...context, signal: abortController.signal };

                    const executePromise = hook.executeAsync(currentImpulse, hookContext);

                    let timer: ReturnType<typeof setTimeout> | undefined;
                    const timeoutPromise = new Promise<never>((_, reject) => {
                        timer = setTimeout(() => {
                            abortController.abort();
                            reject(new Error(`Hook ${hook.name} timeout`));
                        }, hook.timeoutMs);
                    });
                    try {
                        result = await Promise.race([executePromise, timeoutPromise]);
                    } finally {
                        if (timer !== undefined) clearTimeout(timer);
                    }
                } else {
                    result = await hook.executeAsync(currentImpulse, context);
                }

                if (result) {
                    currentImpulse = result;
                } else {
                    // Filter 拦截
                    currentImpulse = null;
                }
            } catch (error) {
                console.error(`[HookChain ${this.name}] Hook ${hook.name} 执行失败:`, error);

                // 标记失败状态
                if (currentImpulse) {
                    currentImpulse.status = MessageStatus.FAILED;
                    currentImpulse.metadata['error_hook'] = hook.name;
                    currentImpulse.metadata['error_message'] = error instanceof Error ? error.message : String(error);
                    currentImpulse.metadata['hook_execution_status'] = HookExecutionStatus.FAILED;
                }

                // 把异常抛出，让外层的 Worker 错误处理器接管
                throw error;
            }
        }

        return currentImpulse;
    }
}

/**
 * 通用的简单异步 Hook 实现基类
 */
export abstract class BaseAsyncHook implements AsyncHook {
    public name: string;
    public hookType: HookType;
    public priority: number;
    public enabled: boolean;
    public timeoutMs: number;

    constructor(
        name: string,
        hookType: HookType,
        priority: number = 0,
        timeoutMs: number = 5000
    ) {
        this.name = name;
        this.hookType = hookType;
        this.priority = priority;
        this.enabled = true;
        this.timeoutMs = timeoutMs;
    }

    public enable(): void {
        this.enabled = true;
    }

    public disable(): void {
        this.enabled = false;
    }

    public abstract executeAsync(impulse: NeuralImpulse, context: HookContext): Promise<NeuralImpulse | null>;
}
