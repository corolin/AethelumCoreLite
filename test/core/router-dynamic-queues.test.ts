import { describe, expect, test, beforeEach } from "bun:test";
import { CoreLiteRouter } from "../../src/core/router.js";
import { NeuralImpulse } from "../../src/core/message.js";
import { AsyncSynapticQueue } from "../../src/core/queue.js";
import { AsyncAxonWorker } from "../../src/core/worker.js";
import { HookPluginRegistry } from "../../src/hooks/runtime.js";

/** 最小可实例化 Worker（仅用于验证 registerWorker 的队列注册语义） */
class MinimalWorker extends AsyncAxonWorker {
    protected async process(_impulse: NeuralImpulse): Promise<void> {
        /* no-op */
    }
}

/**
 * F1/F2（v1.1.1）：动态 durable 队列官方路径 + 自动建队补登记
 *
 * 语义要求：
 *   ensureQueue(definition) —— 运行时官方建队 API：
 *     - 幂等（已存在直接返回同一实例）
 *     - 注入 onDiscard（丢弃归宿登记，与 boot 期 registerQueue 同语义）
 *     - 提供 hookRegistry 时按 definition.hookPlugins 挂插件（WAL 等）
 *   registerWorker —— worker 的输入队列同样获得 onDiscard（不再裸 queues.set）
 *   routeMessage 自动建队 —— 同样注入 onDiscard
 */
describe("CoreLiteRouter - Dynamic Durable Queues (v1.1.1 F1/F2)", () => {
    let router: CoreLiteRouter;

    beforeEach(() => {
        router = new CoreLiteRouter(false);
        router.activate();
    });

    test("ensureQueue(): 创建队列并注入 onDiscard（registerQueue 语义）", async () => {
        const q = await router.ensureQueue({ id: "Q_DYN_A", capacity: 10 });
        expect(q.queueId).toBe("Q_DYN_A");
        expect((q as any).onDiscard).toBeDefined();
        // 注册进路由表：可直接 routeMessage
        const impulse = new NeuralImpulse({ actionIntent: "Q_DYN_A" });
        const ok = await router.routeMessage(impulse, "Q_DYN_A");
        expect(ok).toBe(true);
        expect(q.size()).toBe(1);
    });

    test("ensureQueue(): 幂等——二次调用返回同一实例", async () => {
        const q1 = await router.ensureQueue({ id: "Q_DYN_B", capacity: 10 });
        const q2 = await router.ensureQueue({ id: "Q_DYN_B", capacity: 10 });
        expect(q2).toBe(q1);
    });

    test("ensureQueue(): 提供 hookRegistry 时按 hookPlugins 挂插件", async () => {
        let setupCalls = 0;
        const registry = new HookPluginRegistry();
        registry.register({
            id: "test-probe",
            setup: () => {
                setupCalls++;
                return { hooks: [] };
            },
        });
        const r = new CoreLiteRouter({
            enableWal: false,
            skipBuiltInQueues: true,
            hookRegistry: registry,
        });
        const q = await r.ensureQueue({
            id: "Q_DYN_PLUG",
            capacity: 10,
            hookPlugins: [{ plugin: "test-probe" }],
        });
        expect(q.queueId).toBe("Q_DYN_PLUG");
        expect(setupCalls).toBe(1);
        expect((q as any).onDiscard).toBeDefined();
    });

    test("registerWorker(): worker 输入队列获得 onDiscard 注入", async () => {
        const queue = new AsyncSynapticQueue("Q_WORKER_OWN", 10, false);
        const worker = new MinimalWorker("w-dyn-1", queue, router);
        router.registerWorker(worker);
        expect((queue as any).onDiscard).toBeDefined();
    });

    test("routeMessage(): 自动建队同样注入 onDiscard（F2）", async () => {
        const impulse = new NeuralImpulse({ actionIntent: "AUTO_CREATED_Q" });
        const ok = await router.routeMessage(impulse, "AUTO_CREATED_Q");
        expect(ok).toBe(true);
        const autoQ = (router as any).queues.get("AUTO_CREATED_Q") as AsyncSynapticQueue;
        expect(autoQ).toBeDefined();
        expect((autoQ as any).onDiscard).toBeDefined();
    });
});
