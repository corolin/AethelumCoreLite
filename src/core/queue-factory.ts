import type {
    HookAssemblyDefinition,
    HookPluginMount,
    HookPluginRegistry,
    HookPluginSpec,
} from "../hooks/runtime.js";
import { AsyncSynapticQueue } from "./queue.js";

export interface QueueDefinition {
    id: string;
    capacity?: number;
    autoExpand?: boolean;
    evictOldestOnFull?: boolean;
    shrinkIntervalMs?: number;
    hooks?: HookAssemblyDefinition;
    hookPlugins?: HookPluginSpec[];
    tags?: string[];
    metadata?: Record<string, unknown>;
}

export class ConfigurableQueueFactory {
    constructor(private readonly hookRegistry?: HookPluginRegistry) {}

    public async createQueue(definition: QueueDefinition): Promise<AsyncSynapticQueue> {
        const isLifecycleSink = definition.id === 'Q_FINISH' || definition.id === 'Q_SINK';

        // 终点寄存器队列：默认环形淘汰防内存泄漏，禁止自动无界扩容
        const autoExpand = isLifecycleSink ? false : (definition.autoExpand ?? true);
        const evictOldestOnFull = isLifecycleSink
            ? (definition.evictOldestOnFull ?? true)
            : (definition.evictOldestOnFull ?? false);
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

        let specs = this.hookRegistry
            ? this.hookRegistry.materializeAssembly({
                ...(definition.hooks ?? {}),
                plugins: [
                    ...(definition.hooks?.plugins ?? []),
                    ...(definition.hookPlugins ?? []),
                ],
            })
            : [];

        // 终点登记队列绝不挂载 WAL 插件，防止无消费者时无界落盘且永不清理
        if (isLifecycleSink && specs.length > 0) {
            specs = specs.filter(s => s.plugin !== 'wal');
        }

        if (this.hookRegistry && specs.length > 0) {
            const mount: Partial<HookPluginMount> = {};
            if (definition.tags) {
                mount.tags = definition.tags;
            }
            if (definition.metadata) {
                mount.metadata = definition.metadata;
            }
            await queue.attachHookPlugins(this.hookRegistry, specs, mount);
        }

        return queue;
    }
}
