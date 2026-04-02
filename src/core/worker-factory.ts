import type {
    HookAssemblyDefinition,
    HookPluginMount,
    HookPluginRegistry,
} from "../hooks/runtime.js";
import { AsyncAxonWorker } from "./worker.js";

export interface WorkerDefinition {
    id?: string;
    hooks?: HookAssemblyDefinition;
    tags?: string[];
    metadata?: Record<string, unknown>;
}

export class ConfigurableWorkerFactory {
    constructor(private readonly hookRegistry?: HookPluginRegistry) {}

    public async configureWorker<TWorker extends AsyncAxonWorker>(
        worker: TWorker,
        definition: WorkerDefinition = {},
    ): Promise<TWorker> {
        if (definition.id && definition.id !== worker.id) {
            throw new Error(
                `Worker definition id mismatch: expected ${definition.id}, got ${worker.id}`,
            );
        }

        if (this.hookRegistry && definition.hooks) {
            const mount: Partial<HookPluginMount> = {};
            if (definition.tags) {
                mount.tags = definition.tags;
            }
            if (definition.metadata) {
                mount.metadata = definition.metadata;
            }
            const specs = this.hookRegistry.materializeAssembly(definition.hooks);
            await worker.attachHookPlugins(this.hookRegistry, specs, mount);
        }

        return worker;
    }
}
