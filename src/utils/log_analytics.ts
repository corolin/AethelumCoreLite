import { Database } from 'bun:sqlite';
import { LogEntry, LogLevel } from './structured_logger';
import { join } from 'path';

export enum TimeWindow {
    MINUTE_1 = 60,
    MINUTE_5 = 300,
    MINUTE_15 = 900,
    HOUR_1 = 3600,
    HOUR_6 = 21600,
    HOUR_24 = 86400,
    DAY_1 = 86400,
    WEEK_1 = 604800
}

export class LogAggregator {
    private db: Database;

    constructor(dbPath: string = 'logs_analytics.db') {
        this.db = new Database(dbPath, { create: true });
        this.initDatabase();
    }

    private initDatabase() {
        this.db.run(`
      CREATE TABLE IF NOT EXISTS log_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp REAL NOT NULL,
        level TEXT NOT NULL,
        logger_name TEXT NOT NULL,
        message TEXT NOT NULL,
        module TEXT,
        function TEXT,
        line_number INTEGER,
        thread_id INTEGER,
        thread_name TEXT,
        process_id INTEGER,
        session_id TEXT,
        correlation_id TEXT,
        user_id TEXT,
        request_id TEXT,
        tags TEXT,
        metadata TEXT,
        exception TEXT,
        created_at REAL DEFAULT (strftime('%s', 'now'))
      )
    `);

        // Indices
        this.db.run('CREATE INDEX IF NOT EXISTS idx_timestamp ON log_entries(timestamp)');
        this.db.run('CREATE INDEX IF NOT EXISTS idx_level ON log_entries(level)');
    }

    public addLogEntry(entry: LogEntry) {
        const insert = this.db.prepare(`
      INSERT INTO log_entries (
        timestamp, level, logger_name, message, session_id, correlation_id, 
        tags, metadata, exception
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);

        const tagsJson = entry.tags ? JSON.stringify(entry.tags) : null;
        const metadataJson = entry.metadata ? JSON.stringify(entry.metadata) : null;
        const exceptionJson = entry.exception ? JSON.stringify(entry.exception) : null;

        insert.run(
            entry.timestamp,
            LogLevel[entry.level],
            entry.logger_name,
            entry.message,
            entry.session_id || null,
            entry.correlation_id || null,
            tagsJson,
            metadataJson,
            exceptionJson
        );
    }

    public getLogStatistics(timeWindow: TimeWindow = TimeWindow.HOUR_24): any {
        const endTime = Date.now() / 1000;
        const startTime = endTime - timeWindow;

        const overallQuery = this.db.query(`
      SELECT 
        COUNT(*) as total_logs,
        COUNT(DISTINCT logger_name) as unique_loggers,
        COUNT(DISTINCT session_id) as unique_sessions,
        AVG(LENGTH(message)) as avg_message_length
      FROM log_entries
      WHERE timestamp BETWEEN ? AND ?
    `);
        const overall = overallQuery.get(startTime, endTime);

        const levelQuery = this.db.query(`
      SELECT level, COUNT(*) as count
      FROM log_entries
      WHERE timestamp BETWEEN ? AND ?
      GROUP BY level
      ORDER BY count DESC
    `);
        const by_level = levelQuery.all(startTime, endTime);

        const loggerQuery = this.db.query(`
      SELECT logger_name, COUNT(*) as count
      FROM log_entries
      WHERE timestamp BETWEEN ? AND ?
      GROUP BY logger_name
      ORDER BY count DESC
      LIMIT 10
    `);
        const by_logger = loggerQuery.all(startTime, endTime);

        return {
            overall,
            by_level,
            by_logger
        };
    }
}

let globalAggregator: LogAggregator | null = null;
export const getLogAggregator = () => {
    if (!globalAggregator) globalAggregator = new LogAggregator();
    return globalAggregator;
};
