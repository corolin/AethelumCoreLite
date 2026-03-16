import { describe, expect, test, beforeEach, spyOn } from "bun:test";
import { CoreLiteRouter } from "../../src/core/router.js";
import { NeuralImpulse } from "../../src/core/message.js";
import { AsyncSynapticQueue } from "../../src/core/queue.js";

describe("CoreLiteRouter - Unit Tests", () => {
    let router: CoreLiteRouter;

    beforeEach(() => {
        router = new CoreLiteRouter(false);
        router.activate(); // Router needs to be active to route messages
    });

    test("injectInput() forces route to Q_AUDIT_INPUT", async () => {
        const spy = spyOn(router, "routeMessage").mockResolvedValue(true);
        const impulse = new NeuralImpulse({ actionIntent: "anything" });

        await router.injectInput(impulse);

        expect(impulse.actionIntent).toBe("Q_AUDIT_INPUT");
        expect(spy).toHaveBeenCalledWith(impulse, "Q_AUDIT_INPUT");
    });

    test("routeMessage() standard delivery", async () => {
        const queue = new AsyncSynapticQueue("TEST_QUEUE", 10, false);
        router.registerQueue(queue);

        const impulse = new NeuralImpulse({ actionIntent: "TEST_QUEUE" });
        const success = await router.routeMessage(impulse, "TEST_QUEUE");

        expect(success).toBe(true);
        expect(queue.size()).toBe(1);

        const retrieved = await queue.asyncGet(10);
        expect(retrieved?.messageId).toBe(impulse.messageId);
        expect(retrieved?.metadata["current_queue"]).toBe("TEST_QUEUE");
    });

    test("Security: Block direct access to Q_RESPONSE_SINK from invalid source", async () => {
        const impulse = new NeuralImpulse({
            actionIntent: "Q_RESPONSE_SINK",
            sourceAgent: "HackerAgent"
        });

        await router.routeMessage(impulse, "Q_RESPONSE_SINK");

        // Should be diverted to built-in Q_ERROR
        const qError = (router as any).queues.get("Q_ERROR") as AsyncSynapticQueue;
        const retrievedError = await qError.asyncGet(10);
        expect(retrievedError).not.toBeNull();
        expect(retrievedError?.messageId).toBe(impulse.messageId);
        expect(impulse.metadata["routing_error"]).toContain("Security violation");
    });

    test("Security: Allow access to Q_RESPONSE_SINK from AuditOutputWorker", async () => {
        const impulse = new NeuralImpulse({
            actionIntent: "Q_RESPONSE_SINK",
            sourceAgent: "AuditOutputWorker"
        });

        await router.routeMessage(impulse, "Q_RESPONSE_SINK");

        // Should reach built-in sink successfully
        const qSink = (router as any).queues.get("Q_RESPONSE_SINK") as AsyncSynapticQueue;
        const retrieved = await qSink.asyncGet(10);
        expect(retrieved).not.toBeNull();
        expect(retrieved?.messageId).toBe(impulse.messageId);
    });

    test("Special Routing: AuditInputWorker going to output redirects to audited input", async () => {
        const impulse = new NeuralImpulse({
            actionIntent: "Q_AUDIT_OUTPUT",
            sourceAgent: "AuditInputWorker"
        });

        await router.routeMessage(impulse, "Q_AUDIT_OUTPUT");

        // Should reach built-in Q_AUDITED_INPUT
        const qAuditedInput = (router as any).queues.get("Q_AUDITED_INPUT") as AsyncSynapticQueue;
        const retrieved = await qAuditedInput.asyncGet(10);
        expect(retrieved).not.toBeNull();
        expect(retrieved?.messageId).toBe(impulse.messageId);
        expect(impulse.actionIntent).toBe("Q_AUDITED_INPUT");
        expect(impulse.metadata["current_queue"]).toBe("Q_AUDIT_OUTPUT");
    });

    test("Unregistered queue creates dynamically on route fallback", async () => {
        const impulse = new NeuralImpulse({ actionIntent: "UNKNOWN_QUEUE" });

        await router.routeMessage(impulse, "UNKNOWN_QUEUE");

        const qDynamo = (router as any).queues.get("UNKNOWN_QUEUE") as AsyncSynapticQueue;
        expect(qDynamo).toBeDefined();

        const retrieved = await qDynamo.asyncGet(10);
        expect(retrieved).not.toBeNull();
        expect(retrieved?.messageId).toBe(impulse.messageId);
    });
    test("getQueueMetrics() returns metrics for all queues and workers", () => {
        const metrics = router.getQueueMetrics();
        expect(metrics.queues["Q_ERROR"]).toBeDefined();
        expect(metrics.workers).toBeDefined();
    });
});
