import { beforeEach, describe, expect, test } from "bun:test";
import { AsyncSynapticQueue } from "../../src/core/queue.js";
import { ConfigurableQueueFactory } from "../../src/core/queue-factory.js";
import { CoreLiteRouter } from "../../src/core/router.js";
import { NeuralImpulse } from "../../src/core/message.js";
import { AsyncAxonWorker } from "../../src/core/worker.js";
import { ConfigurableWorkerFactory } from "../../src/core/worker-factory.js";
import { BaseAsyncHook } from "../../src/hooks/chain.js";
import { HookPluginRegistry } from "../../src/hooks/runtime.js";
import { HookType } from "../../src/hooks/types.js";

class PrefixQueueHook extends BaseAsyncHook {
    constructor(private readonly prefix: string) {
        super(`prefix:${prefix}`, HookType.QUEUE_BEFORE_PUT, 0, 0);
    }

    async executeAsync(impulse: NeuralImpulse): Promise<NeuralImpulse | null> {
        impulse.content = `${this.prefix}${impulse.content ?? ""}`;
        return impulse;
    }
}

class WorkerPostfixHook extends BaseAsyncHook {
    constructor(private readonly suffix: string) {
        super(`suffix:${suffix}`, HookType.POST_PROCESS, 0, 0);
    }

    async executeAsync(impulse: NeuralImpulse): Promise<NeuralImpulse | null> {
        impulse.content = `${impulse.content ?? ""}${this.suffix}`;
        return impulse;
    }
}

class HookedWorker extends AsyncAxonWorker {
    protected async process(impulse: NeuralImpulse): Promise<void> {
        impulse.content = `${impulse.content ?? ""}|processed`;
    }
}

describe("Hook plugin runtime", () => {
    let registry: HookPluginRegistry;

    beforeEach(() => {
        registry = new HookPluginRegistry();
    });

    test("queue plugins can be attached declaratively", async () => {
        registry.register({
            id: "prefixer",
            supports: (mount) => mount.kind === "queue",
            setup: (_mount, options) => ({
                hooks: [new PrefixQueueHook(String(options.prefix ?? "plugin:"))],
            }),
        });

        const queue = new AsyncSynapticQueue("Q_PLUGIN_TEST", 10, false);
        await queue.attachHookPlugins(registry, [{ plugin: "prefixer", options: { prefix: "hook:" } }]);

        await queue.asyncPut(new NeuralImpulse({ actionIntent: "test", content: "body" }));
        const dequeued = await queue.asyncGet(100);

        expect(dequeued?.content).toBe("hook:body");
        await queue.stop();
    });

    test("queue factory supports metadata-driven plugin assembly", async () => {
        registry.register({
            id: "tagged-prefixer",
            supports: (mount) => mount.kind === "queue" && mount.tags?.includes("chat") === true,
            setup: () => ({
                hooks: [new PrefixQueueHook("chat:")],
            }),
        });

        const factory = new ConfigurableQueueFactory(registry);
        const queue = await factory.createQueue({
            id: "Q_DYNAMIC",
            capacity: 8,
            tags: ["chat"],
            hookPlugins: [{ plugin: "tagged-prefixer" }],
        });

        await queue.asyncPut(new NeuralImpulse({ actionIntent: "test", content: "hello" }));
        const item = await queue.asyncGet(100);

        expect(queue.maxSize).toBe(8);
        expect(item?.content).toBe("chat:hello");
        await queue.stop();
    });

    test("worker plugins are routed to the correct hook chains", async () => {
        registry.register({
            id: "worker-postfix",
            supports: (mount) => mount.kind === "worker",
            setup: () => ({
                hooks: [new WorkerPostfixHook("|hooked")],
            }),
        });

        const router = new CoreLiteRouter(false);
        const inputQueue = new AsyncSynapticQueue("Q_WORKER_PLUGIN", 10, false);
        const worker = new HookedWorker("HookedWorker", inputQueue, router);
        await worker.attachHookPlugins(registry, [{ plugin: "worker-postfix" }]);

        const impulse = new NeuralImpulse({ actionIntent: "Done", content: "seed" });
        await (worker as any).processImpulse(impulse);

        expect(impulse.content).toBe("seed|processed|hooked");

        await worker.stop();
        await inputQueue.stop();
    });

    test("profiles can assemble reusable hook bundles", async () => {
        registry.register({
            id: "prefixer",
            supports: (mount) => mount.kind === "queue",
            setup: (_mount, options) => ({
                hooks: [new PrefixQueueHook(String(options.prefix ?? "plugin:"))],
            }),
        });
        registry.register({
            id: "worker-postfix",
            supports: (mount) => mount.kind === "worker",
            setup: (_mount, options) => ({
                hooks: [new WorkerPostfixHook(String(options.suffix ?? "|hooked"))],
            }),
        });
        registry.registerProfile("durable-chat", [
            { plugin: "prefixer", options: { prefix: "chat:" } },
        ]);
        registry.registerProfile("post-process-default", [
            { plugin: "worker-postfix", options: { suffix: "|profile" } },
        ]);

        const queueFactory = new ConfigurableQueueFactory(registry);
        const queue = await queueFactory.createQueue({
            id: "Q_PROFILED",
            capacity: 16,
            hooks: { profiles: ["durable-chat"] },
        });

        await queue.asyncPut(new NeuralImpulse({ actionIntent: "test", content: "hello" }));
        const queued = await queue.asyncGet(100);
        expect(queued?.content).toBe("chat:hello");

        const router = new CoreLiteRouter(false);
        const worker = new HookedWorker("ProfiledWorker", queue, router);
        const workerFactory = new ConfigurableWorkerFactory(registry);
        await workerFactory.configureWorker(worker, {
            hooks: { profiles: ["post-process-default"] },
        });

        const impulse = new NeuralImpulse({ actionIntent: "Done", content: "seed" });
        await (worker as any).processImpulse(impulse);
        expect(impulse.content).toBe("seed|processed|profile");

        await worker.stop();
        await queue.stop();
    });
});
