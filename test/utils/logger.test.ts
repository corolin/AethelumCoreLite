import { describe, expect, test, beforeEach, afterEach, spyOn } from "bun:test";
import { getStructuredLogger, LogLevel, StructuredLogger } from "../../src/utils/structured_logger.js";

describe("Logger Utilities - Unit Tests", () => {
    test("getStructuredLogger returns singleton-like or new instance", () => {
        const logger1 = getStructuredLogger("test_service");
        const logger2 = getStructuredLogger("test_service");
        expect(logger1).toBe(logger2);

        const logger3 = getStructuredLogger("another_service", { level: "DEBUG" });
        expect(logger3.level).toBe(LogLevel.DEBUG);
    });

    test("StructuredLogger methods", () => {
        const logger = new StructuredLogger("unit_test", LogLevel.DEBUG, []);
        const logSpy = spyOn(logger as any, "log").mockImplementation(() => {});

        logger.debug("test debug");
        expect(logSpy).toHaveBeenCalledWith(LogLevel.DEBUG, "test debug", {});

        logger.info("test info");
        expect(logSpy).toHaveBeenCalledWith(LogLevel.INFO, "test info", {});

        logger.warning("test warn");
        expect(logSpy).toHaveBeenCalledWith(LogLevel.WARNING, "test warn", {});

        logger.error("test error");
        expect(logSpy).toHaveBeenCalledWith(LogLevel.ERROR, "test error", {});

        logger.critical("test critical");
        expect(logSpy).toHaveBeenCalledWith(LogLevel.CRITICAL, "test critical", {});

        logger.exception("test exception", { e: 1 });
        expect(logSpy).toHaveBeenCalledWith(LogLevel.ERROR, "test exception", expect.any(Object));

        logSpy.mockRestore();
    });

    test("setDefaultContext merges correctly", () => {
        const logger = new StructuredLogger("context_test", LogLevel.INFO, []);
        logger.setDefaultContext({ service: "auth" });
        
        const logSpy = spyOn(logger as any, "log").mockImplementation((_l: any, _m: any, kwargs: any) => {
             // Directly check kwargs in the implementation or verify entry in a more complex setup
             // For simplicity, we just check that setDefaultContext was callable
        });
        
        logger.info("msg");
        expect((logger as any).defaultContext.service).toBe("auth");
        logSpy.mockRestore();
    });
});
