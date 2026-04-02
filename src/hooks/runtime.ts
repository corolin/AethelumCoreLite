import type { AsyncSynapticQueue } from "../core/queue.js";
import type { AsyncAxonWorker } from "../core/worker.js";
import type { AsyncHook } from "./types.js";

export type HookHostKind = "queue" | "worker" | "custom";

export interface HookPluginSpec {
    plugin: string;
    enabled?: boolean;
    priorityOffset?: number;
    options?: Record<string, unknown>;
}

export interface HookAssemblyDefinition {
    plugins?: HookPluginSpec[];
    profiles?: string[];
}

export interface HookPluginMount {
    kind: HookHostKind;
    hostId: string;
    host: unknown;
    queueId?: string;
    workerId?: string;
    tags?: string[];
    metadata?: Record<string, unknown>;
}

export interface HookPluginSetupResult {
    hooks?: AsyncHook[];
    dispose?: (() => void | Promise<void>) | undefined;
}

export interface HookPluginDefinition<TOptions extends Record<string, unknown> = Record<string, unknown>> {
    id: string;
    description?: string;
    supports?: (mount: HookPluginMount) => boolean;
    setup: (
        mount: HookPluginMount,
        options: TOptions,
    ) => HookPluginSetupResult | Promise<HookPluginSetupResult>;
}

export interface HookPluginAttachResult {
    hooks: AsyncHook[];
    disposers: Array<() => void | Promise<void>>;
}

function applyPriorityOffset(hooks: AsyncHook[], offset: number): AsyncHook[] {
    if (!offset) return hooks;
    // 创建新对象而非 mutate 原始 hook，避免同一实例被复用时优先级累积偏移
    return hooks.map((hook) => Object.assign(Object.create(Object.getPrototypeOf(hook)), hook, { priority: hook.priority + offset }));
}

export class HookPluginRegistry {
    private readonly definitions = new Map<string, HookPluginDefinition>();
    private readonly profiles = new Map<string, HookPluginSpec[]>();

    public register<TOptions extends Record<string, unknown>>(definition: HookPluginDefinition<TOptions>): void {
        this.definitions.set(definition.id, definition as HookPluginDefinition);
    }

    public unregister(pluginId: string): boolean {
        return this.definitions.delete(pluginId);
    }

    public has(pluginId: string): boolean {
        return this.definitions.has(pluginId);
    }

    public list(): HookPluginDefinition[] {
        return Array.from(this.definitions.values());
    }

    public registerProfile(profileId: string, specs: HookPluginSpec[]): void {
        this.profiles.set(profileId, specs.map((spec) => ({ ...spec })));
    }

    public unregisterProfile(profileId: string): boolean {
        return this.profiles.delete(profileId);
    }

    public hasProfile(profileId: string): boolean {
        return this.profiles.has(profileId);
    }

    public listProfiles(): Array<{ id: string; specs: HookPluginSpec[] }> {
        return Array.from(this.profiles.entries()).map(([id, specs]) => ({
            id,
            specs: specs.map((spec) => ({ ...spec })),
        }));
    }

    public materializeAssembly(assembly: HookAssemblyDefinition = {}): HookPluginSpec[] {
        const specs: HookPluginSpec[] = [];

        for (const profileId of assembly.profiles ?? []) {
            const profile = this.profiles.get(profileId);
            if (!profile) {
                throw new Error(`Unknown hook plugin profile: ${profileId}`);
            }
            specs.push(...profile.map((spec) => ({ ...spec })));
        }

        for (const spec of assembly.plugins ?? []) {
            specs.push({ ...spec });
        }

        return specs;
    }

    public async resolve(
        mount: HookPluginMount,
        specs: HookPluginSpec[],
    ): Promise<HookPluginAttachResult> {
        const hooks: AsyncHook[] = [];
        const disposers: Array<() => void | Promise<void>> = [];

        for (const spec of specs) {
            if (spec.enabled === false) continue;

            const definition = this.definitions.get(spec.plugin);
            if (!definition) {
                throw new Error(`Unknown hook plugin: ${spec.plugin}`);
            }

            if (definition.supports && !definition.supports(mount)) {
                continue;
            }

            const result = await definition.setup(mount, (spec.options ?? {}) as Record<string, unknown>);
            const pluginHooks = applyPriorityOffset(result.hooks ?? [], spec.priorityOffset ?? 0);
            hooks.push(...pluginHooks);
            if (result.dispose) {
                disposers.push(result.dispose);
            }
        }

        return { hooks, disposers };
    }

    public async resolveAssembly(
        mount: HookPluginMount,
        assembly: HookAssemblyDefinition,
    ): Promise<HookPluginAttachResult> {
        return this.resolve(mount, this.materializeAssembly(assembly));
    }
}

export function createQueuePluginMount(
    queue: AsyncSynapticQueue,
    mount: Partial<HookPluginMount> = {},
): HookPluginMount {
    return {
        kind: "queue",
        hostId: queue.queueId,
        host: queue,
        queueId: queue.queueId,
        tags: mount.tags ?? [],
        metadata: mount.metadata ?? {},
    };
}

export function createWorkerPluginMount(
    worker: AsyncAxonWorker,
    mount: Partial<HookPluginMount> = {},
): HookPluginMount {
    return {
        kind: "worker",
        hostId: worker.id,
        host: worker,
        queueId: worker.getInputQueue().queueId,
        workerId: worker.id,
        tags: mount.tags ?? [],
        metadata: mount.metadata ?? {},
    };
}

export async function disposeHookPluginDisposers(
    disposers: Array<() => void | Promise<void>>,
): Promise<void> {
    while (disposers.length > 0) {
        const disposer = disposers.pop();
        if (!disposer) continue;
        await disposer();
    }
}
