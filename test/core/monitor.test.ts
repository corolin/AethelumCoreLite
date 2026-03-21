import { describe, expect, test, beforeEach, afterEach, mock, spyOn } from "bun:test";
import { AsyncWorkerMonitor } from "../../src/core/monitor.js";
import { AsyncAxonWorker, WorkerState } from "../../src/core/worker.js";
import { CoreLiteRouter } from "../../src/core/router.js";
import { AsyncSynapticQueue } from "../../src/core/queue.js";

describe("AsyncWorkerMonitor - Unit Tests", () => {
    let monitor: AsyncWorkerMonitor;
    let router: CoreLiteRouter;
    let worker: AsyncAxonWorker;
    let queue: AsyncSynapticQueue;

    beforeEach(() => {
        router = new CoreLiteRouter(false);
        queue = new AsyncSynapticQueue("TEST_IN", 10, false, false);
        worker = new AsyncAxonWorker("TestWorker", queue, router);
        monitor = new AsyncWorkerMonitor({
            checkIntervalMs: 50,
            errorThreshold: 2,
            recoveryDelayMs: 100,
            autoRecovery: false // IMPORTANT: Let the first test sit in ERROR state
        });
        monitor.registerWorker(worker);
    });

    afterEach(async () => {
        monitor.stop();
        await worker.stop();
        await router.stop();
    });

    test("registerWorker() initializes metrics", () => {
        const metrics = monitor.getGlobalMetrics();
        expect(metrics["TestWorker"]).toBeDefined();
        expect(metrics["TestWorker"]!.healthScore).toBe(100);
    });

    test("Health check detects errors and triggers circuit breaker", async () => {
        const errorSpy = spyOn(console, "error").mockImplementation(() => {});
        
        // Simulating errors and ensure worker is RUNNING to trigger circuit breaker
        worker.state = WorkerState.RUNNING;
        (worker as any).internalErrorCount = 5; 
        
        monitor.start();
        
        // Wait for a few cycles
        await new Promise(r => setTimeout(r, 200)); 
        
        expect(worker.state as any).toBe(WorkerState.ERROR);
        const metrics = monitor.getGlobalMetrics();
        expect(metrics["TestWorker"]!.healthScore).toBeLessThan(100);
        
        errorSpy.mockRestore();
    });

    test("Auto recovery restarts worker", async () => {
        // const errorSpy = spyOn(console, "error").mockImplementation(() => {});
        
        monitor.stop();
        monitor = new AsyncWorkerMonitor({ 
            checkIntervalMs: 20, 
            errorThreshold: 1, 
            recoveryDelayMs: 50,
            autoRecovery: true
        });
        monitor.registerWorker(worker);
        
        worker.state = WorkerState.RUNNING;
        (worker as any).internalErrorCount = 5;
        monitor.start();
        
        // Wait for it to hit ERROR state
        let retries = 50;
        while ((worker.state as any) !== WorkerState.ERROR && retries > 0) {
            await new Promise(r => setTimeout(r, 20));
            retries--;
        }
        expect(worker.state as any).toBe(WorkerState.ERROR);
        
        // Wait for recovery
        retries = 50;
        while ((worker.state as any) !== WorkerState.RUNNING && retries > 0) {
            await new Promise(r => setTimeout(r, 20));
            retries--;
        }
        expect(worker.state as any).toBe(WorkerState.RUNNING);
        
        // errorSpy.mockRestore();
    });

    test("Timeout detection for inactive workers", async () => {
        monitor.stop();
        monitor = new AsyncWorkerMonitor({ 
            checkIntervalMs: 20, 
            timeoutMs: 50 
        });
        monitor.registerWorker(worker);
        
        (worker as any).lastActiveTimestamp = Date.now() - 200;
        worker.state = WorkerState.RUNNING;

        
        monitor.start();
        await new Promise(r => setTimeout(r, 100));
        
        const metrics = monitor.getGlobalMetrics();
        expect(metrics["TestWorker"]!.isTimedOut).toBe(true);
        expect(monitor.hasTimedOutWorkers()).toBe(true);
        expect(monitor.getTimedOutWorkers()).toContain("TestWorker");
    });
});
