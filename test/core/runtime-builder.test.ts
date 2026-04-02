import { describe, expect, test } from "bun:test";
import { NeuralImpulse } from "../../src/core/message.js";
import { CoreLiteRuntimeBuilder } from "../../src/core/runtime-builder.js";
import { AsyncAxonWorker } from "../../src/core/worker.js";
import { HookPluginRegistry } from "../../src/hooks/runtime.js";
import { BaseAsyncHook } from "../../src/hooks/chain.js";
import { HookType } from "../../src/hooks/types.js";

class PrefixHook extends BaseAsyncHook {
    constructor(private readonly prefix: string) {
        super(`prefix:${prefix}`, HookType.QUEUE_BEFORE_PUT, 0, 0);
    }

    async executeAsync(impulse: NeuralImpulse): Promise<NeuralImpulse | null> {
        impulse.content = `${this.prefix}${impulse.content ?? ""}`;
        return impulse;
    }
}

class SuffixHook extends BaseAsyncHook {
    constructor(private readonly suffix: string) {
        super(`suffix:${suffix}`, HookType.POST_PROCESS, 0, 0);
    }

    async executeAsync(impulse: NeuralImpulse): Promise<NeuralImpulse | null> {
        impulse.content = `${impulse.content ?? ""}${this.suffix}`;
        return impulse;
    }
}

class DemoWorker extends AsyncAxonWorker {
    protected async process(impulse: NeuralImpulse): Promise<void> {
        impulse.content = `${impulse.content ?? ""}|processed`;
    }
}

describe("CoreLiteRuntimeBuilder", () => {
    test("builds router with built-in queues and extra configured queues", async () => {
        const registry = new HookPluginRegistry();
        registry.register({
            id: "prefixer",
            supports: (mount) => mount.kind === "queue",
            setup: () => ({ hooks: [new PrefixHook("built:")] }),
        });
        registry.registerProfile("builtin-profile", [{ plugin: "prefixer" }]);

        const builder = new CoreLiteRuntimeBuilder(registry);
        const { router, queues } = await builder.build({
            router: {
                enableWal: false,
                builtInQueues: [
                    { id: "Q_AUDIT_INPUT", capacity: 1000 },
                    { id: "Q_DONE", capacity: 1000, autoExpand: false },
                    { id: "Q_RESPONSE_SINK", capacity: 1000, autoExpand: false },
                ],
            },
            queues: [
                {
                    id: "Q_CUSTOM",
                    capacity: 4,
                    hooks: { profiles: ["builtin-profile"] },
                },
            ],
        });

        expect((router as any).queues.has("Q_AUDIT_INPUT")).toBe(true);
        expect((router as any).queues.has("Q_CUSTOM")).toBe(true);

        const queue = queues.get("Q_CUSTOM");
        expect(queue).toBeDefined();
        await queue!.asyncPut(new NeuralImpulse({ actionIntent: "test", content: "hello" }));
        const item = await queue!.asyncGet(100);
        expect(item?.content).toBe("built:hello");

        await router.stop();
    });

    test("configures workers before router registration", async () => {
        const registry = new HookPluginRegistry();
        registry.register({
            id: "worker-suffix",
            supports: (mount) => mount.kind === "worker",
            setup: () => ({ hooks: [new SuffixHook("|configured")] }),
        });
        registry.registerProfile("worker-profile", [{ plugin: "worker-suffix" }]);

        const builder = new CoreLiteRuntimeBuilder(registry);
        const { router, queues } = await builder.build({
            router: {
                enableWal: false,
                builtInQueues: [],
            },
            queues: [{ id: "Q_INPUT", capacity: 10, autoExpand: false }],
        });

        const worker = new DemoWorker("DemoWorker", queues.get("Q_INPUT")!, router);
        await builder.registerWorkers(router, [
            {
                worker,
                definition: {
                    hooks: { profiles: ["worker-profile"] },
                },
            },
        ]);

        const impulse = new NeuralImpulse({ actionIntent: "Done", content: "seed" });
        await (worker as any).processImpulse(impulse);
        expect(impulse.content).toBe("seed|processed|configured");

        await router.stop();
    });
});
