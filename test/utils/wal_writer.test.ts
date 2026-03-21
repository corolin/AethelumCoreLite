import { describe, expect, test, beforeEach, afterEach, spyOn } from "bun:test";
import { ImprovedWALWriter, LSNAllocator, WALPtrTracker } from "../../src/utils/wal_writer.js";
import fs from 'fs';
import path from 'path';
import os from 'os';

describe("WAL Utilities - Unit Tests", () => {
    test("LSNAllocator increments correctly", () => {
        const alloc = new LSNAllocator(100);
        expect(alloc.nextLsn()).toBe(100);
        expect(alloc.nextLsn()).toBe(101);
        expect(alloc.getCurrentLsn()).toBe(102);
    });

    test("WALPtrTracker saves and loads LSN", async () => {
        const ptrFile = path.join(os.tmpdir(), `test_ptr_${Date.now()}.ptr`);
        const tracker = new WALPtrTracker(ptrFile);
        
        try {
            await tracker.start();
            expect(tracker.getCommittedLsn()).toBe(0);
            
            await tracker.commitLsn(500);
            expect(tracker.getCommittedLsn()).toBe(500);
            
            // Reload
            const tracker2 = new WALPtrTracker(ptrFile);
            await tracker2.start();
            expect(tracker2.getCommittedLsn()).toBe(500);
        } finally {
            if (fs.existsSync(ptrFile)) fs.unlinkSync(ptrFile);
        }
    });

    test("ImprovedWALWriter write and recovery (ptrTracker path)", async () => {
        const walDir = path.join(os.tmpdir(), `test_wal_${Date.now()}`);
        const writer = new ImprovedWALWriter("test_q", walDir, true, 1024);
        
        try {
            await writer.start();
            const lsn = await writer.writeLog1("msg1", 1, { data: "hello" });
            expect(lsn).toBe(1);
            
            // Simulate crash by creating new writer on same dir without commit
            const writer2 = new ImprovedWALWriter("test_q", walDir, true, 1024);
            const recovered = await writer2.start();
            expect(recovered.length).toBe(1);
            expect(recovered[0]!.lsn).toBe(1);
            expect(JSON.parse(recovered[0]!.payload).data).toBe("hello");
            
            // Commit via legacy writeLog2 (ptrTracker path)
            writer2.writeLog2("msg1", 1);
            await writer2.stop();
            
            // Should not recover anything now
            const writer3 = new ImprovedWALWriter("test_q", walDir, true, 1024);
            const recovered2 = await writer3.start();
            expect(recovered2.length).toBe(0);
        } finally {
            if (fs.existsSync(walDir)) fs.rmSync(walDir, { recursive: true });
        }
    });

    test("writeDelete: tombstone 标记后不应再恢复该消息", async () => {
        const walDir = path.join(os.tmpdir(), `test_wal_del_${Date.now()}`);
        const writer = new ImprovedWALWriter("test_q", walDir, true, 1024 * 1024);

        try {
            await writer.start();
            const lsn1 = await writer.writeLog1("msg1", 1, { data: "alpha" });
            const lsn2 = await writer.writeLog1("msg2", 2, { data: "beta" });
            expect(lsn1).toBe(1);
            expect(lsn2).toBe(2);

            // 仅删除 msg1，msg2 保留（模拟乱序移交场景）
            writer.writeDelete(lsn1!);
            // 等待异步写入完成
            await new Promise(r => setTimeout(r, 50));
            await writer.stop();

            // 崩溃恢复：只应恢复 msg2
            const writer2 = new ImprovedWALWriter("test_q", walDir, true, 1024 * 1024);
            const recovered = await writer2.start();
            expect(recovered.length).toBe(1);
            expect(recovered[0]!.lsn).toBe(lsn2);
            expect(JSON.parse(recovered[0]!.payload).data).toBe("beta");
            await writer2.stop();
        } finally {
            if (fs.existsSync(walDir)) fs.rmSync(walDir, { recursive: true });
        }
    });

    test("writeDelete: 旧段文件全量 tombstone 后应被压缩清理", async () => {
        const walDir = path.join(os.tmpdir(), `test_wal_compact_${Date.now()}`);
        // 极小段大小，强制产生多个段文件
        const writer = new ImprovedWALWriter("test_q", walDir, true, 100);

        try {
            await writer.start();
            const lsn1 = await writer.writeLog1("msg1", 1, { long: "A".repeat(80) });
            const lsn2 = await writer.writeLog1("msg2", 1, { long: "B".repeat(80) });

            const qDir = path.join(walDir, "test_q");
            // msg1/msg2 各自撑满一个段，至少存在 seg 0 和 seg 1
            const seg0Path = path.join(qDir, "log1_000000.wal");
            expect(fs.existsSync(seg0Path)).toBe(true);

            // 删除 seg 0 中的 msg1，使 seg 0 全量 tombstone
            writer.writeDelete(lsn1!);
            await new Promise(r => setTimeout(r, 50));
            await writer.stop();

            // 重新启动触发压缩：seg 0 应被删除
            const writer2 = new ImprovedWALWriter("test_q", walDir, true, 100);
            const recovered = await writer2.start();

            // seg 0 应已被压缩清理
            expect(fs.existsSync(seg0Path)).toBe(false);
            // msg2 应仍可恢复
            expect(recovered.length).toBe(1);
            expect(recovered[0]!.lsn).toBe(lsn2);

            await writer2.stop();
        } finally {
            if (fs.existsSync(walDir)) fs.rmSync(walDir, { recursive: true });
        }
    });

    test("WAL Rotation", async () => {
        const walDir = path.join(os.tmpdir(), `test_wal_rot_${Date.now()}`);
        const writer = new ImprovedWALWriter("test_q", walDir, true, 100); // Tiny segment size
        
        try {
            await writer.start();
            // Each log entry is roughly 50-60 bytes with metadata
            await writer.writeLog1("id1", 1, { long: "A".repeat(80) });
            await writer.writeLog1("id2", 1, { long: "B".repeat(80) });
            
            const files = fs.readdirSync(path.join(walDir, "test_q")).filter(f => f.endsWith('.wal'));
            expect(files.length).toBeGreaterThan(1);
        } finally {
            if (fs.existsSync(walDir)) fs.rmSync(walDir, { recursive: true });
        }
    });
    test("ImprovedWALWriter parser errors and commit failure", async () => {
        const walDir = path.join(os.tmpdir(), `test_wal_err_${Date.now()}`);
        const writer = new ImprovedWALWriter("test_q", walDir, true, 1024);
        
        try {
            await writer.start();
            
            // Mock a failed commit to trigger console.error
            const spy = spyOn(console, "error").mockImplementation(() => {});
            (writer as any).ptrTracker.commitLsn = async () => { throw new Error("Commit failed"); };
            
            writer.writeLog2("msg1", 1);
            // Wait for debounce timer
            await new Promise(r => setTimeout(r, 600));
            expect(spy).toHaveBeenCalled();
            
            // Test parser with bad lines
            expect((writer as any).parseRecord("bad line")).toBeNull();
            expect((writer as any).parseRecord("1|2|3|4")).toBeNull(); // Checksum mismatch
            
            spy.mockRestore();
        } finally {
            if (fs.existsSync(walDir)) fs.rmSync(walDir, { recursive: true });
        }
    });
});
