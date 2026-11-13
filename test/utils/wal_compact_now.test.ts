import { describe, expect, test } from "bun:test";
import { ImprovedWALWriter } from "../../src/utils/wal_writer.js";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

/**
 * v1.1.1 F3：WAL 段压缩的运维 API compactNow()
 * 语义：立即执行一次压缩（与写路径互斥）；已 DEL 的条目物理移除，不再被重放；
 *       未启用 WAL 时 no-op。
 */
describe("ImprovedWALWriter - compactNow() (v1.1.1 F3)", () => {
    test("压缩后重放：已 DEL 条目不再出现，存活条目保留", async () => {
        const dir = mkdtempSync(join(tmpdir(), "wal-compact-"));
        const w = new ImprovedWALWriter("Q_TEST_COMPACT", dir, true);
        await w.start();
        const lsn1 = await w.writeLog1("m1", 2, { marker: "MARKER_ONE" });
        await w.writeLog1("m2", 2, { marker: "MARKER_TWO" });
        expect(lsn1).not.toBeNull();
        await w.writeDelete(lsn1!);
        await w.compactNow();
        w.stop();

        const w2 = new ImprovedWALWriter("Q_TEST_COMPACT", dir, true);
        const recovered = await w2.start();
        w2.stop();

        expect(recovered.some(e => e.payload.includes("MARKER_TWO"))).toBe(true);
        expect(recovered.some(e => e.payload.includes("MARKER_ONE"))).toBe(false);

        rmSync(dir, { recursive: true, force: true });
    });

    test("未启用 WAL 时 compactNow() 为 no-op，不抛错", async () => {
        const dir = mkdtempSync(join(tmpdir(), "wal-noop-"));
        const w = new ImprovedWALWriter("Q_TEST_NOOP", dir, false);
        await w.compactNow();
        w.stop();
        rmSync(dir, { recursive: true, force: true });
        expect(true).toBe(true);
    });
});
