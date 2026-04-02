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
    shrinkIntervalMs?: number;
    hooks?: HookAssemblyDefinition;
    hookPlugins?: HookPluginSpec[];
    tags?: string[];
    metadata?: Record<string, unknown>;
}

export class ConfigurableQueueFactory {
    constructor(private readonly hookRegistry?: HookPluginRegistry) {}

    public async createQueue(definition: QueueDefinition): Promise<AsyncSynapticQueue> {
        const queue = new AsyncSynapticQueue(
            definition.id,
            definition.capacity ?? 0,
            definition.autoExpand ?? true,
            definition.shrinkIntervalMs ?? 10 * 60 * 1000,
        );

        const specs = this.hookRegistry
            ? this.hookRegistry.materializeAssembly({
                ...(definition.hooks ?? {}),
                plugins: [
                    ...(definition.hooks?.plugins ?? []),
                    ...(definition.hookPlugins ?? []),
                ],
            })
            : [];

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
