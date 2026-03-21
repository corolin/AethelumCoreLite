import { mkdirSync, existsSync, appendFileSync, statSync, renameSync, unlinkSync } from 'fs';
import { dirname } from 'path';

export enum LogLevel {
    DEBUG = 0,
    INFO = 1,
    WARNING = 2,
    ERROR = 3,
    CRITICAL = 4
}

export const parseLogLevel = (levelStr: string): LogLevel => {
    const map: Record<string, LogLevel> = {
        'DEBUG': LogLevel.DEBUG,
        'INFO': LogLevel.INFO,
        'WARNING': LogLevel.WARNING,
        'WARN': LogLevel.WARNING,
        'ERROR': LogLevel.ERROR,
        'CRITICAL': LogLevel.CRITICAL,
        'FATAL': LogLevel.CRITICAL
    };
    return map[levelStr.toUpperCase()] ?? LogLevel.INFO;
};

/** 与 `getStructuredLogger(name, { format })` 对应；`format: 'plain'` 与 {@link LogFormat.PLAIN} 等价 */
export enum LogFormat {
    JSON = "json",
    PLAIN = "plain",
    STRUCTURED = "structured",
    ELASTIC = "elastic"
}

export interface LogEntry {
    timestamp: number;
    level: LogLevel;
    logger_name: string;
    message: string;
    module?: string;
    function?: string;
    line_number?: number;
    thread_id?: number;
    thread_name?: string;
    process_id?: number;
    session_id?: string;
    correlation_id?: string;
    user_id?: string;
    request_id?: string;
    tags?: string[];
    metadata?: Record<string, any>;
    exception?: Record<string, any>;
}

export abstract class LogFormatter {
    abstract format(entry: LogEntry): string;
}

export class JsonFormatter extends LogFormatter {
    constructor(private pretty: boolean = false) {
        super();
    }

    format(entry: LogEntry): string {
        const data = {
            ...entry,
            level: LogLevel[entry.level],
            timestamp_iso: new Date(entry.timestamp * 1000).toISOString(),
        };
        return this.pretty ? JSON.stringify(data, null, 2) : JSON.stringify(data);
    }
}

export class PlainFormatter extends LogFormatter {
    constructor(private include_metadata: boolean = false) {
        super();
    }

    format(entry: LogEntry): string {
        const timestamp = new Date(entry.timestamp * 1000).toISOString().replace('T', ' ').slice(0, 19);
        let base_msg = `${timestamp} - [${LogLevel[entry.level]}] - ${entry.logger_name} - ${entry.message}`;

        if (entry.module) {
            base_msg = `${timestamp} - [${LogLevel[entry.level]}] - ${entry.logger_name} - (${entry.module}:${entry.line_number}) - ${entry.message}`;
        }

        if (this.include_metadata && entry.metadata && Object.keys(entry.metadata).length > 0) {
            const metaStr = Object.entries(entry.metadata).map(([k, v]) => `${k}=${v}`).join(' | ');
            base_msg += ` | ${metaStr}`;
        }

        if (entry.tags && entry.tags.length > 0) {
            const tagsStr = entry.tags.map(t => `#${t}`).join(' ');
            base_msg += ` [${tagsStr}]`;
        }

        return base_msg;
    }
}

export abstract class LogOutput {
    abstract write(formatted_entry: string, entry: LogEntry): void;
    close(): void { }
}

export class ConsoleOutput extends LogOutput {
    constructor(private use_colors: boolean = true) {
        super();
    }

    write(formatted_entry: string, entry: LogEntry): void {
        if (this.use_colors) {
            const colors: Record<number, string> = {
                [LogLevel.DEBUG]: '\x1b[36m',
                [LogLevel.INFO]: '\x1b[32m',
                [LogLevel.WARNING]: '\x1b[33m',
                [LogLevel.ERROR]: '\x1b[31m',
                [LogLevel.CRITICAL]: '\x1b[35m',
            };
            const reset = '\x1b[0m';
            const color = colors[entry.level] || '';
            const output = entry.level >= LogLevel.ERROR ? console.error : console.log;
            output(`${color}${formatted_entry}${reset}`);
        } else {
            if (entry.level >= LogLevel.ERROR) {
                console.error(formatted_entry);
            } else {
                console.log(formatted_entry);
            }
        }
    }
}

export class FileOutput extends LogOutput {
    private filePath: string;
    private maxSize: number;
    private backupCount: number;

    constructor(filePath: string, maxSize = 50 * 1024 * 1024, backupCount = 10) {
        super();
        this.filePath = filePath;
        this.maxSize = maxSize;
        this.backupCount = backupCount;

        const dir = dirname(filePath);
        if (!existsSync(dir)) {
            mkdirSync(dir, { recursive: true });
        }
    }

    write(formatted_entry: string, entry: LogEntry): void {
        if (existsSync(this.filePath)) {
            const stats = statSync(this.filePath);
            if (stats.size >= this.maxSize) {
                this.rotateFiles();
            }
        }
        appendFileSync(this.filePath, formatted_entry + '\n', 'utf8');
    }

    private rotateFiles(): void {
        const oldest = `${this.filePath}.${this.backupCount}`;
        if (existsSync(oldest)) unlinkSync(oldest);

        for (let i = this.backupCount - 1; i > 0; i--) {
            const oldBackup = `${this.filePath}.${i}`;
            const newBackup = `${this.filePath}.${i + 1}`;
            if (existsSync(oldBackup)) renameSync(oldBackup, newBackup);
        }
        if (existsSync(this.filePath)) {
            renameSync(this.filePath, `${this.filePath}.1`);
        }
    }
}

export class StructuredLogger {
    private defaultContext: Record<string, any> = {};

    constructor(
        public name: string,
        public level: LogLevel = LogLevel.INFO,
        public outputs: LogOutput[] = [],
        public formatter: LogFormatter = new JsonFormatter()
    ) { }

    setLevel(level: LogLevel) {
        this.level = level;
    }

    addOutput(output: LogOutput) {
        this.outputs.push(output);
    }

    setDefaultContext(context: Record<string, any>) {
        Object.assign(this.defaultContext, context);
    }

    private log(level: LogLevel, message: string, kwargs: any = {}) {
        if (level < this.level) return;

        const entry: LogEntry = {
            timestamp: Date.now() / 1000,
            level,
            logger_name: this.name,
            message,
            metadata: { ...this.defaultContext, ...kwargs.metadata },
            tags: kwargs.tags || [],
            process_id: process.pid,
            // Stack traces and module extraction are omitted in simple TS version 
            // but could be added via Error().stack
        };

        if (kwargs.exc_info) {
            entry.exception = { message: String(kwargs.exc_info) };
        }

        const formatted = this.formatter.format(entry);
        for (const output of this.outputs) {
            output.write(formatted, entry);
        }
    }

    debug(message: string, kwargs: any = {}) { this.log(LogLevel.DEBUG, message, kwargs); }
    info(message: string, kwargs: any = {}) { this.log(LogLevel.INFO, message, kwargs); }
    warning(message: string, kwargs: any = {}) { this.log(LogLevel.WARNING, message, kwargs); }
    error(message: string, kwargs: any = {}) { this.log(LogLevel.ERROR, message, kwargs); }
    critical(message: string, kwargs: any = {}) { this.log(LogLevel.CRITICAL, message, kwargs); }
    exception(message: string, kwargs: any = {}) { this.error(message, { ...kwargs, exc_info: true }); }

    close() {
        for (const output of this.outputs) {
            output.close();
        }
    }
}

// Global logger manager
class LoggerManager {
    private loggers = new Map<string, StructuredLogger>();
    private globalConfig: any = {};

    createLogger(name: string, config: any = {}): StructuredLogger {
        if (this.loggers.has(name)) return this.loggers.get(name)!;

        const finalConfig = { ...this.globalConfig, ...config };
        const outputs: LogOutput[] = [];

        if (finalConfig.console !== false) {
            outputs.push(new ConsoleOutput(finalConfig.console_colors !== false));
        }

        if (finalConfig.file?.path) {
            outputs.push(new FileOutput(
                finalConfig.file.path,
                finalConfig.file.max_size,
                finalConfig.file.backup_count
            ));
        }

        const usePlain =
            finalConfig.format === LogFormat.PLAIN ||
            finalConfig.format === 'plain';
        const formatter = usePlain ? new PlainFormatter() : new JsonFormatter();

        const logger = new StructuredLogger(
            name,
            finalConfig.level ? parseLogLevel(finalConfig.level) : LogLevel.INFO,
            outputs,
            formatter
        );

        if (finalConfig.default_context) {
            logger.setDefaultContext(finalConfig.default_context);
        }

        this.loggers.set(name, logger);
        return logger;
    }

    getLogger(name: string): StructuredLogger {
        if (!this.loggers.has(name)) {
            return this.createLogger(name);
        }
        return this.loggers.get(name)!;
    }
}

const manager = new LoggerManager();
export const getStructuredLogger = (name: string, config?: any) => {
    if (config) {
        return manager.createLogger(name, config);
    }
    return manager.getLogger(name);
};
