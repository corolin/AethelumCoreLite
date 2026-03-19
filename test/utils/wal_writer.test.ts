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

    test("ImprovedWALWriter write and recovery", async () => {
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
            
            // Now commit the LSN
            writer2.writeLog2("msg1", 1);
            // Wait for debounce or force stop
            await writer2.stop();
            
            // Should not recover anything now
            const writer3 = new ImprovedWALWriter("test_q", walDir, true, 1024);
            const recovered2 = await writer3.start();
            expect(recovered2.length).toBe(0);
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
