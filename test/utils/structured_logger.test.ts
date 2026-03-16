import { describe, expect, test, beforeEach, afterEach, spyOn, mock } from "bun:test";
import { 
    StructuredLogger, 
    LogLevel, 
    JsonFormatter, 
    PlainFormatter, 
    ConsoleOutput, 
    FileOutput,
    parseLogLevel 
} from "../../src/utils/structured_logger.js";
import fs from 'fs';
import path from 'path';
import os from 'os';

describe("StructuredLogger - Unit Tests", () => {
    test("parseLogLevel helper", () => {
        expect(parseLogLevel("DEBUG")).toBe(LogLevel.DEBUG);
        expect(parseLogLevel("info")).toBe(LogLevel.INFO);
        expect(parseLogLevel("warn")).toBe(LogLevel.WARNING);
        expect(parseLogLevel("ERROR")).toBe(LogLevel.ERROR);
        expect(parseLogLevel("CRITICAL")).toBe(LogLevel.CRITICAL);
        expect(parseLogLevel("unknown")).toBe(LogLevel.INFO);
    });

    test("JsonFormatter logic", () => {
        const formatter = new JsonFormatter();
        const entry = {
            timestamp: 1600000000,
            level: LogLevel.INFO,
            logger_name: "test",
            message: "msg"
        };
        const formatted = formatter.format(entry);
        const parsed = JSON.parse(formatted);
        expect(parsed.message).toBe("msg");
        expect(parsed.level).toBe("INFO");
        expect(parsed.timestamp_iso).toBeDefined();
    });

    test("PlainFormatter logic", () => {
        const formatter = new PlainFormatter(true);
        const entry = {
            timestamp: 1600000000,
            level: LogLevel.WARNING,
            logger_name: "test_logger",
            message: "warn msg",
            metadata: { key: "val" },
            tags: ["tag1"]
        };
        const formatted = formatter.format(entry);
        expect(formatted).toContain("[WARNING]");
        expect(formatted).toContain("test_logger");
        expect(formatted).toContain("warn msg");
        expect(formatted).toContain("key=val");
        expect(formatted).toContain("[#tag1]");
    });

    test("StructuredLogger level filtering", () => {
        const mockWrite = mock((_f: string, _e: any) => {});
        const mockOutput = {
            write: mockWrite,
            close: () => {}
        };
        const logger = new StructuredLogger("test", LogLevel.WARNING, [mockOutput as any]);

        logger.info("should not log");
        expect(mockWrite).not.toHaveBeenCalled();

        logger.warning("should log");
        expect(mockWrite).toHaveBeenCalled();
    });

    test("FileOutput and rotation", async () => {
        const tempLog = path.join(os.tmpdir(), `test_rotation_${Date.now()}.log`);
        const output = new FileOutput(tempLog, 50, 2); // 50 bytes limit
        
        try {
            const msg = "A".repeat(60); // 60 bytes > 50 bytes
            output.write(msg, { level: LogLevel.INFO } as any);
            expect(fs.existsSync(tempLog)).toBe(true);
            const size = fs.statSync(tempLog).size;
            expect(size).toBeGreaterThanOrEqual(60);
            
            // Second write should trigger rotation because existing file is > 50 bytes
            output.write("B".repeat(10), { level: LogLevel.INFO } as any);
            expect(fs.existsSync(`${tempLog}.1`)).toBe(true);
            expect(fs.readFileSync(tempLog, 'utf8')).toContain("B");
            expect(fs.readFileSync(`${tempLog}.1`, 'utf8')).toContain("A");
        } finally {
            if (fs.existsSync(tempLog)) fs.unlinkSync(tempLog);
            if (fs.existsSync(`${tempLog}.1`)) fs.unlinkSync(`${tempLog}.1`);
        }
    });

    test("ConsoleOutput logging", () => {
        const consoleSpy = spyOn(console, "log").mockImplementation(() => {});
        const errSpy = spyOn(console, "error").mockImplementation(() => {});
        
        const output = new ConsoleOutput(false);
        output.write("test log", { level: LogLevel.INFO } as any);
        expect(consoleSpy).toHaveBeenCalledWith("test log");

        output.write("error log", { level: LogLevel.ERROR } as any);
        expect(errSpy).toHaveBeenCalledWith("error log");
        
        consoleSpy.mockRestore();
        errSpy.mockRestore();
    });
    test("StructuredLogger setLevel and addOutput and close", () => {
        const logger = new StructuredLogger("test", LogLevel.INFO);
        logger.setLevel(LogLevel.ERROR);
        expect(logger.level).toBe(LogLevel.ERROR);
        
        const mockWrite = mock((_f: string, _e: any) => {});
        const mockClose = mock(() => {});
        const mockOutput = {
            write: mockWrite,
            close: mockClose
        };
        
        logger.addOutput(mockOutput as any);
        expect(logger.outputs.length).toBe(1);
        
        logger.error("test error");
        expect(mockWrite).toHaveBeenCalled();
        
        logger.close();
        expect(mockClose).toHaveBeenCalled();
    });
});
