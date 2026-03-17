import { describe, expect, test, beforeEach, afterEach, spyOn } from "bun:test";
import { AsyncAxonWorker, WorkerState } from "../../src/core/worker.js";
import { CoreLiteRouter } from "../../src/core/router.js";
import { AsyncSynapticQueue } from "../../src/core/queue.js";
import { NeuralImpulse, MessageStatus } from "../../src/core/message.js";

class TestWorker extends AsyncAxonWorker {
    public processCalled = false;
    public lastProcessedImpulse: NeuralImpulse | null = null;

    protected async process(impulse: NeuralImpulse): Promise<void> {
        this.processCalled = true;
        this.lastProcessedImpulse = impulse;

        // Manual routing to test proxy
        if (impulse.content === "route_me") {
            await this.routeAndDone(impulse, "Q_DONE");
        }
    }
}

class AutoRoutingTestWorker extends AsyncAxonWorker {
    protected async process(impulse: NeuralImpulse): Promise<void> {
        // Do not call routeAndDone, allow base class to auto-route based on actionIntent
    }
}

describe("AsyncAxonWorker - Unit Tests", () => {
    let router: CoreLiteRouter;
    let inputQueue: AsyncSynapticQueue;
    let worker: TestWorker;

    beforeEach(() => {
        router = new CoreLiteRouter();
        inputQueue = new AsyncSynapticQueue("TEST_IN", 10, false);
        router.registerQueue(inputQueue);
        worker = new TestWorker("TestAgent", inputQueue, router);
        router.registerWorker(worker);
    });

    afterEach(async () => {
        await worker.stop();
        await router.stop();
    });

    test("start() and stop() manage state correctly", async () => {
        expect(worker.state).toBe(WorkerState.INITIALIZING);

        await worker.start();
        expect(worker.state).toBe(WorkerState.RUNNING);

        await worker.stop();
        expect(worker.state).toBe(WorkerState.STOPPED);
    });

    test("processImpulse() executes pre and post hooks", async () => {
        const preSpy = spyOn(worker.getPreHooks(), "executeHooks");
        const postSpy = spyOn(worker.getPostHooks(), "executeHooks");

        await worker.start();

        const impulse = new NeuralImpulse({ actionIntent: "test_action", content: "hello" });
        await inputQueue.asyncPut(impulse);

        // Wait for worker loop to pick it up
        await new Promise(r => setTimeout(r, 50));

        expect(preSpy).toHaveBeenCalled();
        expect(worker.processCalled).toBe(true);
        expect(worker.lastProcessedImpulse?.content).toBe("hello");
        expect(postSpy).toHaveBeenCalled();
    });

    test("routeAndDone() prevents duplicate auto-routing", async () => {
        router.activate();
        const routerSpy = spyOn(router, "routeMessage");

        await worker.start();

        const impulse = new NeuralImpulse({ actionIntent: "original_intent", content: "route_me" });
        await inputQueue.asyncPut(impulse);

        await new Promise(r => setTimeout(r, 50));

        // It should have been routed ONCE by routeAndDone inside process()
        expect(routerSpy).toHaveBeenCalledTimes(1);
        const routeArgs = routerSpy.mock.calls[0] as any[];
        expect(routeArgs[1]).toBe("Q_DONE");
    });

    test("Base class auto-routes if child doesn't route manually", async () => {
        router.activate();
        const autoWorker = new AutoRoutingTestWorker("AutoAgent", inputQueue, router);
        const routerSpy = spyOn(router, "routeMessage");

        await autoWorker.start();

        const qDefault = new AsyncSynapticQueue("DEFAULT_TARGET", 10, false);
        router.registerQueue(qDefault);

        const impulse = new NeuralImpulse({ actionIntent: "DEFAULT_TARGET", content: "auto_route" });
        await inputQueue.asyncPut(impulse);

        await new Promise(r => setTimeout(r, 50));

        // Should be auto-routed to actionIntent DEFAULT_TARGET
        expect(routerSpy).toHaveBeenCalledTimes(1);
        const routeArgs = routerSpy.mock.calls[0] as any[];
        expect(routeArgs[1]).toBe("DEFAULT_TARGET");

        await autoWorker.stop();
    });
    test("Base class default process() is a no-op", async () => {
        // Create a worker without overriding process
        const bareWorker = new (class extends AsyncAxonWorker { })("BareAgent", inputQueue, router);
        const impulse = new NeuralImpulse({ actionIntent: "Done" });
        
        // This should not throw
        await (bareWorker as any).processImpulse(impulse);
    });

    test("runLoop error handling", async () => {
        const spy = spyOn(console, "error").mockImplementation(() => {});
        // Mock asyncGet to throw
        inputQueue.asyncGet = async () => { throw new Error("Loop fail"); };
        
        await worker.start();
        await new Promise(r => setTimeout(r, 60)); // Let loop run
        
        expect(worker.state).toBe(WorkerState.RUNNING); // Loop continues but logs error
        expect(spy).toHaveBeenCalledWith(expect.stringContaining("处理循环异常"), expect.any(Error));
        
        spy.mockRestore();
    });

    test("runLoop fatal error log (outer catch)", async () => {
        const spy = spyOn(console, "error").mockImplementation(() => {});
        // Mock runLoop to throw immediately (before its own try-catch)
        const originalRunLoop = (worker as any).runLoop;
        (worker as any).runLoop = async () => { throw new Error("Fatal loop"); };
        
        await worker.start();
        // The catch block is async, wait a bit
        await new Promise(r => setTimeout(r, 20));
        
        expect(worker.state).toBe(WorkerState.ERROR);
        expect(spy).toHaveBeenCalledWith(expect.stringContaining("发生致命错误"), expect.any(Error));
        
        spy.mockRestore();
        (worker as any).runLoop = originalRunLoop;
    });

    test("validateSinkSecurity coverage", async () => {
        const impulse = new NeuralImpulse({ actionIntent: "NotSink" });
        // Should hit the "return true" at the end of validateSinkSecurity
        const result = (worker as any).validateSinkSecurity(impulse);
        expect(result).toBe(true);
    });
});
