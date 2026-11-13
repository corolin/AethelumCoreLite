import { BaseAsyncHook } from './chain.js';
import { HookType } from './types.js';
import { NeuralImpulse } from '../core/message.js';
import { ImprovedWALWriter } from '../utils/wal_writer.js';
import type { AsyncSynapticQueue } from '../core/queue.js';
import type { HookContext } from './types.js';
import type { HookPluginDefinition } from './runtime.js';

/**
 * WAL 持久化钩子集合
 * 封装了 ImprovedWALWriter，并提供 Pre/Post 两个钩子切面
 */
export class WALHookManager {
    private walWriter: ImprovedWALWriter;
    private queueId: string;

    constructor(queueId: string, walDir: string = "wal_data_v2") {
        this.queueId = queueId;
        this.walWriter = new ImprovedWALWriter(queueId, walDir, true);
    }

    /**
     * 启动 WAL 并将未处理的消息恢复到队列中
     */
    public async startAndReplay(queue: AsyncSynapticQueue): Promise<void> {
        const recovered = await this.walWriter.start();
        for (const entry of recovered) {
            queue.internalReplay(entry);
        }
        if (recovered.length > 0) {
            console.log(`[WAL ${this.queueId}] 崩溃恢复：已重放到内存队列 ${recovered.length} 条记录`);
        }
    }

    /**
     * 创建入队前钓子 (写 Log1)
     */
    public createPrePutHook(): BaseAsyncHook {
        const self = this;
        return new class extends BaseAsyncHook {
            constructor() {
                super(`WAL_PRE_${self.queueId}`, HookType.QUEUE_BEFORE_PUT, 100);
            }
            async executeAsync(impulse: NeuralImpulse): Promise<NeuralImpulse | null> {
                const priority = impulse.priority ?? 2;
                const lsn = await self.walWriter.writeLog1(impulse.messageId, priority, impulse.toDict());
                if (lsn !== null) {
                    impulse.metadata['wal_lsn'] = lsn;
                }
                return impulse;
            }
        };
    }

    /**
     * 创建确认后钓子 (写 Delete/Log2)
     */
    public createAfterAckHook(): BaseAsyncHook {
        const self = this;
        return new class extends BaseAsyncHook {
            constructor() {
                super(`WAL_POST_${self.queueId}`, HookType.QUEUE_AFTER_ACK, 100);
            }
            async executeAsync(impulse: NeuralImpulse, context: HookContext): Promise<NeuralImpulse | null> {
                // 优先使用上下文中的显式 LSN（通常来自源队列确认，即移交成功后的 tombstone）
                const explicitLsn = context.explicitLsn as number | undefined;
                let targetLsn = explicitLsn;

                if (targetLsn === undefined) {
                    // 无显式来源 LSN：覆盖“过期/拦截直接丢弃”等未移交场景的兜底删除。
                    // 此时消息尚未进入下一跳，wal_lsn 仍为本队列 pre-put 写入的值，
                    // 必须校验归属后再删，防止误把其他队列的 LSN 当作本队列记录 tombstone。
                    const fallbackLsn = impulse.metadata['wal_lsn'] as number | undefined;
                    if (fallbackLsn !== undefined) {
                        if (self.walWriter.ownsLsn(fallbackLsn)) {
                            targetLsn = fallbackLsn;
                        } else {
                            console.warn(
                                `[WAL ${self.queueId}] confirmDelivery 缺少来源 LSN，且 wal_lsn=${fallbackLsn} 不属于本队列，已跳过 tombstone（防止误删）`,
                            );
                        }
                    }
                }

                if (targetLsn !== undefined) {
                    await self.walWriter.writeDelete(targetLsn);
                }
                return impulse;
            }
        };
    }

    public async stop(): Promise<void> {
        await this.walWriter.stop();
    }
}

export function createWalHookPlugin(defaultWalDir: string = "wal_data_v2"): HookPluginDefinition<{ walDir?: string }> {
    return {
        id: "wal",
        description: "Attach WAL replay and queue lifecycle hooks.",
        supports: (mount) => mount.kind === "queue",
        setup: async (mount, options) => {
            const queue = mount.host as AsyncSynapticQueue;
            const manager = new WALHookManager(queue.queueId, options.walDir ?? defaultWalDir);
            await manager.startAndReplay(queue);
            return {
                hooks: [manager.createPrePutHook(), manager.createAfterAckHook()],
                dispose: async () => manager.stop(),
            };
        },
    };
}
