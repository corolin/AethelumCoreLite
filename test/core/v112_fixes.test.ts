import { describe, it, expect } from "bun:test";
import { CoreLiteRouter } from "../../src/core/router.js";
import { AsyncSynapticQueue } from "../../src/core/queue.js";
import { AsyncAxonWorker } from "../../src/core/worker.js";
import { NeuralImpulse, MessageStatus } from "../../src/core/message.js";
import { AsyncHookChain, BaseAsyncHook } from "../../src/hooks/chain.js";
import { HookType } from "../../src/hooks/types.js";
import { ConfigurableQueueFactory } from "../../src/core/queue-factory.js";
import { HookPluginRegistry } from "../../src/hooks/runtime.js";
import { createWalHookPlugin } from "../../src/hooks/wal_hook.js";

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

describe("AethelumCoreLite v1.1.2 Bug Fixes Regression Suite", () => {
    it("修复 A：毒消息异常不发生死循环自环，process() 仅调用 1 次，正确投递 Q_ERROR", async () => {
        const router = new CoreLiteRouter({ enableWal: false });
        const queue = new AsyncSynapticQueue("Q_POISON_IN", 100, true);
        let processCalls = 0;

        class PoisonWorker extends AsyncAxonWorker {
            protected async process(): Promise<void> {
                processCalls++;
                throw new Error("fatal_poison_error");
            }
        }

        const worker = new PoisonWorker("poison-worker", queue, router);
        router.registerWorker(worker);
        router.activate();

        const impulse = new NeuralImpulse({
            actionIntent: "Q_POISON_IN",
            content: "poison_payload",
            metadata: { custom_tag: "foo" }
        });
        await router.routeMessage(impulse, "Q_POISON_IN");

        // 等待一段时间让事件循环运转
        await sleep(150);
        await router.stop();

        expect(processCalls).toBe(1);
        const report = router.getConservationReport();
        expect(report.created).toBe(1);
        expect(report.errored).toBe(1);
        expect(report.inFlight).toBe(0);
        expect(report.balanced).toBe(true);
    });

    it("修复 B：未路由早退不重投自身输入队列，阻断自环并正常终结", async () => {
        const router = new CoreLiteRouter({ enableWal: false });
        const queue = new AsyncSynapticQueue("Q_SILENT_IN", 100, true);
        let processCalls = 0;

        class SilentWorker extends AsyncAxonWorker {
            protected async process(): Promise<void> {
                processCalls++;
                // 未修改 actionIntent，也未手动路由
            }
        }

        const worker = new SilentWorker("silent-worker", queue, router);
        router.registerWorker(worker);
        router.activate();

        const impulse = new NeuralImpulse({
            actionIntent: "Q_SILENT_IN",
            content: "silent_payload"
        });
        await router.routeMessage(impulse, "Q_SILENT_IN");

        await sleep(150);
        await router.stop();

        expect(processCalls).toBe(1);
        const report = router.getConservationReport();
        expect(report.created).toBe(1);
        expect(report.finished).toBe(1);
        expect(report.inFlight).toBe(0);
        expect(report.balanced).toBe(true);
    });

    it("修复 C：手动路由标记不跨 Worker 泄漏，下游终点 Worker 正常自动登记 FINISH", async () => {
        const router = new CoreLiteRouter({ enableWal: false });
        const qUpstream = new AsyncSynapticQueue("Q_UPSTREAM", 100, true);
        const qDownstream = new AsyncSynapticQueue("Q_DOWNSTREAM", 100, true);
        let downstreamSawFlag: unknown = "not_checked";

        class UpstreamWorker extends AsyncAxonWorker {
            protected async process(i: NeuralImpulse): Promise<void> {
                i.actionIntent = "Done";
                await this.routeAndDone(i, "Q_DOWNSTREAM");
            }
        }

        class DownstreamWorker extends AsyncAxonWorker {
            protected async process(i: NeuralImpulse): Promise<void> {
                downstreamSawFlag = i.metadata["_manually_routed"];
                // 终点 Worker，不手动路由，依赖基类自动完成登记
            }
        }

        router.registerWorker(new UpstreamWorker("upstream", qUpstream, router));
        router.registerWorker(new DownstreamWorker("downstream", qDownstream, router));
        router.activate();

        const impulse = new NeuralImpulse({
            actionIntent: "Q_UPSTREAM",
            content: "handoff_data"
        });
        await router.routeMessage(impulse, "Q_UPSTREAM");

        await sleep(200);
        const report = router.getConservationReport();
        await router.stop();

        expect(downstreamSawFlag).toBeUndefined();
        expect(report.finished).toBe(1);
        expect(report.inFlight).toBe(0);
        expect(report.balanced).toBe(true);
    });

    it("修复：bestEffort 钩子失败不污染消息 status 为 FAILED", async () => {
        const chain = new AsyncHookChain("test_chain");
        class BestEffortFailHook extends BaseAsyncHook {
            constructor() {
                super("fail_hook", HookType.PRE_PROCESS, 10, 5000, true);
            }
            async executeAsync(): Promise<NeuralImpulse | null> {
                throw new Error("harmless_side_effect_error");
            }
        }

        chain.addHook(new BestEffortFailHook());
        const impulse = new NeuralImpulse({ actionIntent: "Q_TEST" });
        impulse.status = MessageStatus.PROCESSING;

        const result = await chain.executeHooks(impulse, HookType.PRE_PROCESS, {
            workerId: "test",
            queueId: "q",
            timestamp: Date.now()
        });

        expect(result).not.toBeNull();
        expect(result!.status).toBe(MessageStatus.PROCESSING);
        expect(result!.metadata["hook_warnings"]).toBeDefined();
        expect(Array.isArray(result!.metadata["hook_warnings"])).toBe(true);
    });

    it("修复：ErrorHandler 保留原脉冲元数据", async () => {
        const router = new CoreLiteRouter({ enableWal: false });
        router.activate();

        const impulse = new NeuralImpulse({
            sessionId: "sess-meta-test",
            actionIntent: "Q_TEST",
            sourceAgent: "SourceA",
            content: "meta_content",
            metadata: {
                platform: "qqbot",
                reply_target: "group-1234",
                ingress_queue: "Q_GATEWAY"
            }
        });

        await router.errorHandler.handleError(new Error("meta_error"), impulse, {
            workerId: "w1",
            queueId: "q1",
            stage: "test"
        });

        const errorQueue = (router as any).queues.get("Q_ERROR") as AsyncSynapticQueue;
        const errImpulse = await errorQueue.asyncGet(100);
        await router.stop();

        expect(errImpulse).not.toBeNull();
        expect(errImpulse!.metadata.platform).toBe("qqbot");
        expect(errImpulse!.metadata.reply_target).toBe("group-1234");
        expect(errImpulse!.metadata.ingress_queue).toBe("Q_GATEWAY");
        expect(errImpulse!.metadata.error_type).toBeDefined();
    });

    it("修复 D：生命周期终点队列 Q_FINISH/Q_SINK 强制禁用 WAL 并使用环形淘汰", async () => {
        const registry = new HookPluginRegistry();
        registry.register(createWalHookPlugin());

        const factory = new ConfigurableQueueFactory(registry);
        // 尝试给 Q_FINISH 挂载 WAL
        const finishQueue = await factory.createQueue({
            id: "Q_FINISH",
            capacity: 20,
            hookPlugins: [{ plugin: "wal" }]
        });

        expect(finishQueue.evictOldestOnFull).toBe(true);
        expect(finishQueue.autoExpand).toBe(false);

        // 验证写入超过 capacity 时自动滑动淘汰最旧消息
        for (let i = 0; i < 35; i++) {
            await finishQueue.asyncPut(new NeuralImpulse({ actionIntent: "Q_FINISH", content: `msg_${i}` }));
        }

        expect(finishQueue.size()).toBe(20);
        expect(finishQueue.getMetrics().totalDropped).toBe(15);
        await finishQueue.stop();
    });

    it("修复：dynamicQueues mode=deny 时拦截未允许的队列创建", async () => {
        const router = new CoreLiteRouter({
            enableWal: false,
            dynamicQueues: {
                mode: "deny",
                allowPatterns: ["ALLOWED_*"],
                defaultCapacity: 100,
                defaultAutoExpand: true,
                defaultShrinkIntervalMs: 60000,
                hooks: { profiles: [], plugins: [] },
                tags: []
            }
        });
        router.activate();

        const deniedImpulse = new NeuralImpulse({ actionIntent: "DENIED_QUEUE" });
        const allowedImpulse = new NeuralImpulse({ actionIntent: "ALLOWED_TASK_1" });

        const deniedResult = await router.routeMessage(deniedImpulse, "DENIED_QUEUE");
        const allowedResult = await router.routeMessage(allowedImpulse, "ALLOWED_TASK_1");
        await router.stop();

        expect(deniedResult).toBe(false);
        expect(allowedResult).toBe(true);
    });
});
