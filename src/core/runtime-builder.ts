import type { HookPluginRegistry } from "../hooks/runtime.js";
import { ConfigurableQueueFactory, type QueueDefinition } from "./queue-factory.js";
import { CoreLiteRouter } from "./router.js";
import type { AsyncSynapticQueue } from "./queue.js";
import { ConfigurableWorkerFactory, type WorkerDefinition } from "./worker-factory.js";
import type { AsyncAxonWorker } from "./worker.js";

export interface RuntimeWorkerRegistration<TWorker extends AsyncAxonWorker = AsyncAxonWorker> {
    worker: TWorker;
    definition?: WorkerDefinition;
}

export interface CoreLiteRuntimeDefinition {
    router?: {
        enableWal?: boolean;
        builtInQueues?: QueueDefinition[];
        skipBuiltInQueues?: boolean;
    };
    queues?: QueueDefinition[];
}

export class CoreLiteRuntimeBuilder {
    private readonly queueFactory: ConfigurableQueueFactory;
    private readonly workerFactory: ConfigurableWorkerFactory;

    constructor(private readonly hookRegistry?: HookPluginRegistry) {
        this.queueFactory = new ConfigurableQueueFactory(hookRegistry);
        this.workerFactory = new ConfigurableWorkerFactory(hookRegistry);
    }

    public async createRouter(definition: CoreLiteRuntimeDefinition = {}): Promise<CoreLiteRouter> {
        const router = new CoreLiteRouter({
            enableWal: definition.router?.enableWal ?? true,
            skipBuiltInQueues: true,
        });
        if (!definition.router?.skipBuiltInQueues) {
            await this.registerQueues(
                router,
                definition.router?.builtInQueues ?? this.getDefaultBuiltInQueueDefinitions(definition),
            );
        }
        return router;
    }

    public async registerQueues(
        router: CoreLiteRouter,
        definitions: QueueDefinition[] = [],
    ): Promise<Map<string, AsyncSynapticQueue>> {
        const queues = new Map<string, AsyncSynapticQueue>();

        for (const definition of definitions) {
            const queue = await this.queueFactory.createQueue(definition);
            router.registerQueue(queue);
            queues.set(definition.id, queue);
        }

        return queues;
    }

    public async registerWorkers(
        router: CoreLiteRouter,
        registrations: RuntimeWorkerRegistration[] = [],
    ): Promise<void> {
        for (const registration of registrations) {
            if (registration.definition) {
                await this.workerFactory.configureWorker(registration.worker, registration.definition);
            }
            router.registerWorker(registration.worker);
        }
    }

    public async build(definition: CoreLiteRuntimeDefinition = {}): Promise<{
        router: CoreLiteRouter;
        queues: Map<string, AsyncSynapticQueue>;
    }> {
        const router = await this.createRouter(definition);
        const queues = await this.registerQueues(router, definition.queues ?? []);
        return { router, queues };
    }

    private getDefaultBuiltInQueueDefinitions(definition: CoreLiteRuntimeDefinition): QueueDefinition[] {
        const durableQueues = [
            "Q_AUDIT_INPUT",
            "Q_AUDITED_INPUT",
            "Q_AUDIT_OUTPUT",
            "Q_ERROR",
            "Q_REFLECTION",
        ];
        const enableWal = definition.router?.enableWal ?? true;

        // 当 registry 中存在 "wal" plugin 且系统启用 WAL 时，自动为 durable queues 注入 WAL hook spec。
        // 这恢复了旧 WALHookManager 直接挂载时的等价行为，调用方只需 registry.register(createWalHookPlugin()) 即可。
        const walPluginSpecs =
            enableWal && this.hookRegistry?.has("wal")
                ? [{ plugin: "wal" }]
                : [];

        const builtIns: QueueDefinition[] = durableQueues.map((id) => ({
            id,
            capacity: 1000,
            autoExpand: true,
            hookPlugins: walPluginSpecs,
        }));
        builtIns.push({
            id: "Q_DONE",
            capacity: 1000,
            autoExpand: false,
        });
        builtIns.push({
            id: "Q_RESPONSE_SINK",
            capacity: 1000,
            autoExpand: false,
        });

        return builtIns;
    }
}
