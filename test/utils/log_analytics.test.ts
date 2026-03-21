import { describe, expect, test, beforeEach, afterEach } from "bun:test";
import { LogAggregator, TimeWindow } from "../../src/utils/log_analytics.js";
import { LogLevel } from "../../src/utils/structured_logger.js";
import fs from 'fs';
import path from 'path';

describe("LogAggregator - Unit Tests", () => {
    let aggregator: LogAggregator;
    const dbPath = ":memory:";

    beforeEach(() => {
        aggregator = new LogAggregator(dbPath);
    });

    afterEach(() => {
        aggregator.close();
    });

    test("addLogEntry() and getLogStatistics()", () => {
        const now = Date.now() / 1000;
        
        aggregator.addLogEntry({
            timestamp: now,
            level: LogLevel.INFO,
            logger_name: "test1",
            message: "msg1",
            session_id: "s1"
        });

        aggregator.addLogEntry({
            timestamp: now - 100,
            level: LogLevel.ERROR,
            logger_name: "test1",
            message: "error msg",
            session_id: "s1"
        });

        const stats = aggregator.getLogStatistics(TimeWindow.HOUR_24);
        
        expect(stats.overall.total_logs).toBe(2);
        expect(stats.overall.unique_loggers).toBe(1);
        expect(stats.by_level.length).toBe(2);
        
        const infoLevel = stats.by_level.find((l: any) => l.level === "INFO");
        expect(infoLevel.count).toBe(1);

        // Coverage for global aggregator getter
        const { getLogAggregator } = require("../../src/utils/log_analytics.js");
        expect(getLogAggregator()).toBeDefined();
    });

    test("TimeWindow filtering", () => {
        const now = Date.now() / 1000;
        
        // Very old log
        aggregator.addLogEntry({
            timestamp: now - (3600 * 2),
            level: LogLevel.INFO,
            logger_name: "old",
            message: "old msg"
        });

        const stats = aggregator.getLogStatistics(TimeWindow.HOUR_1);
        expect(stats.overall.total_logs).toBe(0);
        
        const statsLong = aggregator.getLogStatistics(TimeWindow.HOUR_6);
        expect(statsLong.overall.total_logs).toBe(1);
    });
});
