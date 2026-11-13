import { describe, expect, test } from "bun:test";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { AsyncSynapticQueue, AsyncAxonWorker, CoreLiteRouter, NeuralImpulse } from "../../src/core/index.js";
import { WALHookManager } from "../../src/hooks/wal_hook.js";
import { BaseAsyncHook } from "../../src/hooks/chain.js";
import { HookType } from "../../src/hooks/types.js";
import { ImprovedWALWriter } from "../../src/utils/wal_writer.js";

describe("queue delivery and WAL recovery", () => {
    test("an in-flight message rejected during shutdown replays after restart", async () => {
        const dir = await mkdtemp(join(tmpdir(), "wal-shutdown-"));
        const router = new CoreLiteRouter({ enableWal: false, skipBuiltInQueues: true });
        const queue = new AsyncSynapticQueue("input");
        const wal = new WALHookManager("input", dir);
        const entered = Promise.withResolvers<void>();
        const release = Promise.withResolvers<void>();
        class Worker extends AsyncAxonWorker {
            protected async process() {
                entered.resolve();
                await release.promise;
            }
        }
        try {
            await wal.startAndReplay(queue);
            queue.getHooks().addHooks([wal.createPrePutHook(), wal.createAfterAckHook()]);
            router.registerWorker(new Worker("slow", queue, router));
            router.activate();
            const impulse = new NeuralImpulse({ actionIntent: "next" });
            await router.routeMessage(impulse, "input");
            await entered.promise;
            const stopping = router.stop();
            release.resolve();
            await stopping;
            await wal.stop();
            const reader = new ImprovedWALWriter("input", dir);
            try {
                const records = await reader.start();
                expect(records.map(record => JSON.parse(record.payload).messageId)).toEqual([impulse.messageId]);
            } finally {
                await reader.stop();
            }
        } finally {
            release.resolve();
            await rm(dir, { recursive: true, force: true });
        }
    });

    test("a filtered message is counted once at its final destination", async () => {
        const router = new CoreLiteRouter({ enableWal: false });
        const queue = new AsyncSynapticQueue("filtered");
        class Filter extends BaseAsyncHook {
            async executeAsync() { return null; }
        }
        queue.getHooks().addHook(new Filter("filter", HookType.QUEUE_BEFORE_PUT));
        router.registerQueue(queue);
        router.activate();
        try {
            expect(await router.routeMessage(new NeuralImpulse({ actionIntent: "end" }), "filtered")).toBe(true);
            expect(router.getConservationReport()).toMatchObject({ created: 1, sunk: 1, inFlight: 0, balanced: true });
        } finally {
            await router.stop();
        }
    });

    test("a waiting consumer skips expired input and receives the next live message", async () => {
        const queue = new AsyncSynapticQueue("ttl");
        try {
            const waiting = queue.asyncGet(1000);
            await queue.asyncPut(new NeuralImpulse({ actionIntent: "end", expiresAt: 1 }));
            const live = new NeuralImpulse({ actionIntent: "end" });
            await queue.asyncPut(live);
            expect(await waiting).toBe(live);
            expect(queue.getMetrics()).toMatchObject({ size: 0, totalDropped: 1 });
        } finally {
            await queue.stop();
        }
    });

    test("an unreadable segment aborts compaction before any segment changes", async () => {
        const dir = await mkdtemp(join(tmpdir(), "wal-unreadable-"));
        const writer = new ImprovedWALWriter("q", dir);
        const first = join(dir, "q", "log1_000000.wal");
        const unreadable = join(dir, "q", "log1_000001.wal");
        try {
            await writer.start();
            await writeFile(first, "DEL|1\n");
            await mkdir(unreadable);
            await expect(writer.compactNow()).rejects.toThrow();
            expect(await readFile(first, "utf8")).toBe("DEL|1\n");
        } finally {
            await rm(unreadable, { recursive: true, force: true });
            await writer.stop();
            await rm(dir, { recursive: true, force: true });
        }
    });

    test("repeated deletes do not postpone the first scheduled compaction", async () => {
        const dir = await mkdtemp(join(tmpdir(), "wal-busy-"));
        const writer = new ImprovedWALWriter("q", dir);
        try {
            await writer.start();
            const first = await writer.writeLog1("first", 2, { content: "first" });
            await writer.writeDelete(first!);
            const timer = writer["compactTimer"];
            expect(timer).not.toBeNull();
            const second = await writer.writeLog1("second", 2, { content: "second" });
            await writer.writeDelete(second!);
            expect(writer["compactTimer"]).toBe(timer);
        } finally {
            await writer.stop();
            await rm(dir, { recursive: true, force: true });
        }
    });
});
