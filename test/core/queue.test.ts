import { describe, expect, test, beforeEach, afterEach, spyOn } from "bun:test";
import { AsyncSynapticQueue } from "../../src/core/queue.js";
import { NeuralImpulse, MessagePriority } from "../../src/core/message.js";

describe("AsyncSynapticQueue - Unit Tests", () => {
    let queue: AsyncSynapticQueue;

    beforeEach(() => {
        // Disable WAL for pure memory queue tests
        queue = new AsyncSynapticQueue("test_q", 5, false);
    });

    afterEach(async () => {
        queue.clear();
        await queue.stop();
    });

    test("asyncPut() and asyncGet() basic operations", async () => {
        expect(queue.empty()).toBe(true);

        const impulse = new NeuralImpulse({ actionIntent: "test" });
        const success = await queue.asyncPut(impulse);

        expect(success).toBe(true);
        expect(queue.size()).toBe(1);
        expect(queue.empty()).toBe(false);

        const retrieved = await queue.asyncGet(100);
        expect(retrieved).not.toBeNull();
        expect(retrieved?.messageId).toBe(impulse.messageId);
        expect(queue.size()).toBe(0);
    });

    test("asyncPut() respects maxSize backpressure", async () => {
        // Fill queue
        for (let i = 0; i < 5; i++) {
            const success = await queue.asyncPut(new NeuralImpulse({ actionIntent: `item_${i}` }));
            expect(success).toBe(true);
        }

        expect(queue.size()).toBe(5);

        // Put 6th item
        const overflowSuccess = await queue.asyncPut(new NeuralImpulse({ actionIntent: "overflow" }));
        expect(overflowSuccess).toBe(false);
        expect(queue.size()).toBe(5);

        const metrics = queue.getMetrics();
        expect(metrics.totalDropped).toBe(1);
    });

    test("asyncGet() respects priority sorting", async () => {
        // Put in order: NORMAL, LOW, CRITICAL
        await queue.asyncPut(new NeuralImpulse({ actionIntent: "normal", priority: MessagePriority.NORMAL }));
        await queue.asyncPut(new NeuralImpulse({ actionIntent: "low", priority: MessagePriority.LOW }));
        await queue.asyncPut(new NeuralImpulse({ actionIntent: "critical", priority: MessagePriority.CRITICAL }));

        // CRITICAL is index 0 -> should be fetched first
        const first = await queue.asyncGet(100);
        expect(first?.actionIntent).toBe("critical");

        const second = await queue.asyncGet(100);
        expect(second?.actionIntent).toBe("normal");

        const third = await queue.asyncGet(100);
        expect(third?.actionIntent).toBe("low");
    });

    test("asyncGet() blocks and waits for new item", async () => {
        // Start waiting
        const getPromise = queue.asyncGet(500);

        // Wait a slight bit then put
        setTimeout(() => {
            queue.asyncPut(new NeuralImpulse({ actionIntent: "delayed" }));
        }, 50);

        const result = await getPromise;
        expect(result).not.toBeNull();
        expect(result?.actionIntent).toBe("delayed");
    });

    test("asyncGet() skips expired messages", async () => {
        // Create an expired message
        const expiredImpulse = new NeuralImpulse({ actionIntent: "expired", expiresAt: Date.now() - 1000 });
        const validImpulse = new NeuralImpulse({ actionIntent: "valid" });

        await queue.asyncPut(expiredImpulse);
        await queue.asyncPut(validImpulse);

        expect(queue.size()).toBe(2);

        // The first asyncGet should skip "expired" and return "valid"
        const retrieved = await queue.asyncGet(100);

        expect(retrieved).not.toBeNull();
        expect(retrieved?.actionIntent).toBe("valid");
        expect(queue.size()).toBe(0); // Both processed (one discarded, one returned)
    });
});
