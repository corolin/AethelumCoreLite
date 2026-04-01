import { BaseAsyncHook } from './chain.js';
import { HookType } from './types.js';
import { NeuralImpulse } from '../core/message.js';
import { ImprovedWALWriter } from '../utils/wal_writer.js';
import type { AsyncSynapticQueue } from '../core/queue.js';
import type { HookContext } from './types.js';

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
                // 优先使用上下文中的显式 LSN（通常来自源队列确认）
                const explicitLsn = context.explicitLsn as number | undefined;
                const targetLsn = explicitLsn !== undefined ? explicitLsn : impulse.metadata['wal_lsn'] as number | undefined;

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
