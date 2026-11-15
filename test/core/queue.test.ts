import { describe, expect, test, beforeEach, afterEach, spyOn } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { AsyncSynapticQueue } from "../../src/core/queue.js";
import { NeuralImpulse, MessagePriority } from "../../src/core/message.js";
import { WALHookManager } from "../../src/hooks/wal_hook.js";

describe("AsyncSynapticQueue - Unit Tests", () => {
    let queue: AsyncSynapticQueue;

    beforeEach(() => {
        // Pure memory queue tests with autoExpand disabled for backpressure assertions
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
    test("autoExpand increases capacity", async () => {
        queue = new AsyncSynapticQueue("exp_q", 2, true);
        await queue.asyncPut(new NeuralImpulse({ actionIntent: "i1" }));
        await queue.asyncPut(new NeuralImpulse({ actionIntent: "i2" }));
        
        // 3rd item should trigger expansion
        const success = await queue.asyncPut(new NeuralImpulse({ actionIntent: "i3" }));
        expect(success).toBe(true);
        expect(queue.getMetrics().capacity).toBeGreaterThan(2);
    });

    test("shrinkTimer reduces capacity after base reached", async () => {
        // Use a very short interval to trigger it during test
        queue = new AsyncSynapticQueue("shrink_q", 2, false, 10);
        (queue as any).baseCapacity = 2;
        queue.maxSize = 10;
        (queue as any).metrics.capacity = 10;
        
        // Wait for at least one interval to fire
        await new Promise(r => setTimeout(r, 50));
        
        expect(queue.maxSize).toBe(2);
    });

    test("internalReplay handles corrupted WAL payload gracefully and replays valid entry", async () => {
        const warnSpy = spyOn(console, "warn").mockImplementation(() => {});
        try {
            queue.internalReplay({ lsn: 1, priority: 2, payload: "{corrupted-json" });
            expect(warnSpy).toHaveBeenCalled();
            expect(queue.size()).toBe(0);

            const validImpulse = new NeuralImpulse({
                actionIntent: "replayed",
                priority: MessagePriority.HIGH,
            });
            queue.internalReplay({
                lsn: 2,
                priority: MessagePriority.HIGH,
                payload: JSON.stringify(validImpulse.toDict()),
            });

            expect(queue.size()).toBe(1);
            const retrieved = await queue.asyncGet(100);
            expect(retrieved).not.toBeNull();
            expect(retrieved?.messageId).toBe(validImpulse.messageId);
            expect(retrieved?.actionIntent).toBe("replayed");
            expect(retrieved?.metadata["wal_lsn"]).toBe(2);
        } finally {
            warnSpy.mockRestore();
        }
    });

    test("confirmDelivery handles no WAL context", async () => {
        const impulse = new NeuralImpulse({ actionIntent: "test" });
        // Should not throw
        await queue.confirmDelivery(impulse);
    });

    test("confirmDelivery 缺少来源 LSN 时不误用非本队列 wal_lsn，仅本队列 LSN 允许兜底删除", async () => {
        const dir = await mkdtemp(join(tmpdir(), "wal-confirm-"));
        const walQueue = new AsyncSynapticQueue("wal_confirm_q", 5, false);
        const wal = new WALHookManager("wal_confirm_q", dir);
        await wal.startAndReplay(walQueue);
        walQueue.getHooks().addHooks([wal.createPrePutHook(), wal.createAfterAckHook()]);

        const warnSpy = spyOn(console, "warn").mockImplementation(() => {});
        const writeDeleteSpy = spyOn((wal as any).walWriter, "writeDelete");

        try {
            // 场景 1：无显式来源 LSN，且 wal_lsn 不属于本队列（超出当前分配游标）→ 告警并跳过
            const foreignImpulse = new NeuralImpulse({ actionIntent: "foreign" });
            foreignImpulse.metadata["wal_lsn"] = 999;
            await walQueue.confirmDelivery(foreignImpulse);

            expect(warnSpy).toHaveBeenCalled();
            expect(writeDeleteSpy).not.toHaveBeenCalled();

            // 场景 2：本队列 pre-put 写入获得 wal_lsn=1 → 无显式来源 LSN 时允许兜底删除本队列记录
            const ownedImpulse = new NeuralImpulse({ actionIntent: "owned" });
            const putOk = await walQueue.asyncPut(ownedImpulse);
            expect(putOk).toBe(true);
            expect(ownedImpulse.metadata["wal_lsn"]).toBe(1);

            await walQueue.confirmDelivery(ownedImpulse);
            expect(writeDeleteSpy).toHaveBeenCalledWith(1);
        } finally {
            warnSpy.mockRestore();
            writeDeleteSpy.mockRestore();
            walQueue.clear();
            await walQueue.stop();
            await wal.stop();
            await rm(dir, { recursive: true, force: true });
        }
    });
});
