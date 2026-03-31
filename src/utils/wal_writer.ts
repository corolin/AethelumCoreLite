/**
 * WAL 写入语义说明
 *
 * - **writeDelete（落标）**：向当前 WAL 段追加 DEL|{lsn} 标记。
 *   在 writeMutex 保护下执行。删除操作异步执行不阻塞调用方。
 *   若在 DEL 标记落盘前进程崩溃，重启后对应 Log1 可能再次被恢复（at-least-once 下的重复），非数据丢失。
 * - **段压缩**：由 scheduleCompaction 异步触发，物理移除已有 DEL 标记的 Log1 条目。
 * - **优雅退出**：`stop()` 处理最终压缩并排空写入互斥队列。
 */
import fs from 'fs';
import path from 'path';
import crypto from 'crypto';

class AsyncMutex {
    private promise = Promise.resolve();

    async runExclusive<T>(fn: () => Promise<T>): Promise<T> {
        let resolve: () => void;
        const nextPromise = new Promise<void>(res => { resolve = res; });
        const priorPromise = this.promise;
        this.promise = priorPromise.then(() => nextPromise).catch(() => nextPromise);

        try {
            await priorPromise.catch(() => {}); // 即使前一个失败也继续
            return await fn();
        } finally {
            resolve!();
        }
    }
}

export class LSNAllocator {
    private currentLsn: number;

    constructor(startLsn: number = 1) {
        this.currentLsn = startLsn;
    }

    public nextLsn(): number {
        return this.currentLsn++;
    }

    public getCurrentLsn(): number {
        return this.currentLsn;
    }
}

export class WALPtrTracker {
    private ptrPath: string;
    private committedLsn: number = 0;

    constructor(ptrPath: string) {
        this.ptrPath = ptrPath;
    }

    public async start(): Promise<void> {
        try {
            const data = await fs.promises.readFile(this.ptrPath, 'utf8');
            this.committedLsn = parseInt(data, 10) || 0;
            console.log(`[WAL Tracker] 加载位点 LSN: ${this.committedLsn}`);
        } catch {
            await this.writeLsn(0);
        }
    }

    public getCommittedLsn(): number {
        return this.committedLsn;
    }

    public async commitLsn(lsn: number): Promise<void> {
        this.committedLsn = lsn;
        await this.writeLsn(lsn);
    }

    private async writeLsn(lsn: number): Promise<void> {
        const tmpPath = `${this.ptrPath}.${crypto.randomBytes(4).toString('hex')}.tmp`;
        await fs.promises.writeFile(tmpPath, lsn.toString(), 'utf8');
        await fs.promises.rename(tmpPath, this.ptrPath);
        // 对目录进行同步以确保 rename 持久化
        try {
            const dirFd = await fs.promises.open(path.dirname(this.ptrPath), 'r');
            await dirFd.sync();
            await dirFd.close();
        } catch {}
    }

    public stop(): void {
        console.log(`[WAL Tracker] 停止追踪，最后提交位点: ${this.committedLsn}`);
    }
}

/**
 * WAL 崩溃恢复条目
 */
export interface WALRecoveredEntry {
    lsn: number;
    priority: number;
    payload: string; // JSON string
}

export class ImprovedWALWriter {
    private queueId: string;
    private walDir: string;
    private enableWal: boolean;

    private ptrTracker!: WALPtrTracker;
    private lsnAllocator?: LSNAllocator;

    private currentSegmentPath!: string;
    private currentSegmentNum: number = 0;
    private maxSegmentSize: number;

    // 并发写入保护锁
    private writeMutex = new AsyncMutex();

    // Log2 批量防抖位点确认
    private lastCommittedLsn: number = 0;
    private commitTimer: NodeJS.Timeout | null = null;

    // 压缩防抖
    private compactTimer: NodeJS.Timeout | null = null;
    private compactDebounceMs = 2000;

    constructor(queueId: string, walDir: string = "wal_data_v2", enableWal: boolean = true, maxSegmentSize: number = 100 * 1024 * 1024) {
        this.queueId = queueId;
        this.walDir = path.resolve(process.cwd(), walDir, queueId);
        this.enableWal = enableWal;
        this.maxSegmentSize = maxSegmentSize;
    }

    /**
     * 启动 WAL 系统，返回未提交的条目用于崩溃恢复
     */
    public async start(): Promise<WALRecoveredEntry[]> {
        if (!this.enableWal) return [];

        await fs.promises.mkdir(this.walDir, { recursive: true });

        // 清理上次崩溃可能遗留的临时文件
        await this.cleanupOrphanedTmpFiles();

        this.ptrTracker = new WALPtrTracker(path.join(this.walDir, 'tracker.ptr'));
        await this.ptrTracker.start();

        // 寻找最大的段号，用于初始化 Segment 和 LSN
        const files = (await fs.promises.readdir(this.walDir)).filter(f => f.startsWith('log1_') && f.endsWith('.wal'));
        let maxLsn = this.ptrTracker.getCommittedLsn();

        if (files.length > 0) {
            const segNums = files.map(f => parseInt(f.split('_')[1]!.split('.')[0]!, 10)).sort((a, b) => a - b);
            this.currentSegmentNum = segNums[segNums.length - 1]!;
            const maxLsnFromSegments = await this.scanMaxLsnFromSegments(segNums);
            maxLsn = Math.max(maxLsn, maxLsnFromSegments);
        } else {
            this.currentSegmentNum = 0;
        }

        this.currentSegmentPath = path.join(this.walDir, `log1_${this.currentSegmentNum.toString().padStart(6, '0')}.wal`);
        this.lsnAllocator = new LSNAllocator(maxLsn + 1);

        // 扫描未提交条目用于恢复
        const recovered = await this.scanUncommitted();

        // 启动完成日志
        console.log(`[WAL Writer ${this.queueId}] 启动成功，当前 LSN: ${this.lsnAllocator!.getCurrentLsn()}，段号: ${this.currentSegmentNum}${recovered.length > 0 ? `，待恢复: ${recovered.length} 条` : ''}`);

        return recovered;
    }

    private async scanMaxLsnFromSegments(segNums: number[]): Promise<number> {
        let maxLsn = 0;
        for (const seg of segNums) {
            const segPath = path.join(this.walDir, `log1_${seg.toString().padStart(6, '0')}.wal`);
            try {
                const content = await fs.promises.readFile(segPath, 'utf8');
                for (const line of content.split('\n')) {
                    if (!line || line.startsWith('DEL|')) continue;
                    const firstSep = line.indexOf('|');
                    if (firstSep <= 0) continue;
                    const lsn = parseInt(line.substring(0, firstSep), 10);
                    if (!isNaN(lsn) && lsn > maxLsn) {
                        maxLsn = lsn;
                    }
                }
            } catch {}
        }
        return maxLsn;
    }

    public async writeLog1(messageId: string, priority: number, data: Record<string, any>): Promise<number | null> {
        if (!this.enableWal) return null;
        if (!this.lsnAllocator) throw new Error(`[WAL Writer ${this.queueId}] writeLog1() called before start()`);

        return await this.writeMutex.runExclusive(async () => {
            const lsn = this.lsnAllocator!.nextLsn();
            const payload = JSON.stringify(data);
            const checksum = crypto.createHash('md5').update(payload).digest('hex').substring(0, 8);
            const record = `${lsn}|${checksum}|${Buffer.byteLength(payload)}|${payload}\n`;

            await fs.promises.appendFile(this.currentSegmentPath, record, 'utf8');
            
            // 确保物理同步
            try {
                const fd = await fs.promises.open(this.currentSegmentPath, 'r+');
                await fd.datasync();
                await fd.close();
            } catch {}

            const stats = await fs.promises.stat(this.currentSegmentPath);
            if (stats.size >= this.maxSegmentSize) {
                this.currentSegmentNum++;
                this.currentSegmentPath = path.join(this.walDir, `log1_${this.currentSegmentNum.toString().padStart(6, '0')}.wal`);
                // 对目录进行同步
                try {
                    const dirFd = await fs.promises.open(this.walDir, 'r');
                    await dirFd.sync();
                    await dirFd.close();
                } catch {}
            }

            return lsn;
        });
    }

    public writeLog2(messageId: string, lsn?: number): void {
        if (!this.enableWal || lsn === undefined || lsn === null) return;
        if (!this.ptrTracker) return;

        this.lastCommittedLsn = lsn;

        if (!this.commitTimer) {
            this.commitTimer = setTimeout(() => {
                this.ptrTracker.commitLsn(this.lastCommittedLsn).catch(err => {
                    console.error(`[WAL Writer ${this.queueId}] 提交位点失败:`, err);
                });
                this.commitTimer = null;
            }, 500).unref();
        }
    }

    /**
     * 删除 WAL 记录：向当前段追加 DEL|lsn 标记，不直接进行物理重写以提高响应性能
     */
    public async writeDelete(lsn: number): Promise<void> {
        if (!this.enableWal || !this.lsnAllocator) return;

        return await this.writeMutex.runExclusive(async () => {
            const record = `DEL|${lsn}\n`;
            await fs.promises.appendFile(this.currentSegmentPath, record, 'utf8');
            
            // 确保物理同步
            try {
                const fd = await fs.promises.open(this.currentSegmentPath, 'r+');
                await fd.datasync();
                await fd.close();
            } catch {}

            this.scheduleCompaction();
        }).catch(err => {
            console.error(`[WAL Writer ${this.queueId}] 写入删除标记失败 LSN ${lsn}:`, err);
        });
    }

    private scheduleCompaction() {
        if (this.compactTimer) clearTimeout(this.compactTimer);
        this.compactTimer = setTimeout(() => {
            this.writeMutex.runExclusive(async () => {
                await this.compactWalSegments();
            }).catch(err => {
                console.error(`[WAL Writer ${this.queueId}] 压缩 WAL 失败:`, err);
            });
            this.compactTimer = null;
        }, this.compactDebounceMs).unref();
    }

    private async compactWalSegments() {
        const files = await fs.promises.readdir(this.walDir);
        const segNums = files
            .filter(f => f.startsWith('log1_') && f.endsWith('.wal'))
            .map(f => parseInt(f.split('_')[1]!.split('.')[0]!, 10))
            .sort((a, b) => a - b);
        
        if (segNums.length === 0) return;

        const deletedLsns = new Set<number>();
        const segContent = new Map<number, string[]>();

        // 1. 收集全量 DEL 和 Log1
        for (const seg of segNums) {
            const segPath = path.join(this.walDir, `log1_${seg.toString().padStart(6, '0')}.wal`);
            try {
                const content = await fs.promises.readFile(segPath, 'utf8');
                const lines = content.split('\n').filter(Boolean);
                const log1Lines: string[] = [];
                for (const line of lines) {
                    if (line.startsWith('DEL|')) {
                        const lsn = parseInt(line.substring(4), 10);
                        if (!isNaN(lsn)) deletedLsns.add(lsn);
                    } else {
                        log1Lines.push(line);
                    }
                }
                segContent.set(seg, log1Lines);
            } catch {}
        }

        // 2. 按顺序安全重写
        for (const seg of segNums) {
            const segPath = path.join(this.walDir, `log1_${seg.toString().padStart(6, '0')}.wal`);
            const log1Lines = segContent.get(seg) || [];
            const keptLines = log1Lines.filter(line => {
                const lsn = parseInt(line.split('|')[0]!, 10);
                return !deletedLsns.has(lsn);
            });

            try {
                if (keptLines.length === 0) {
                    if (seg === this.currentSegmentNum) {
                        await fs.promises.writeFile(segPath, '', 'utf8');
                    } else {
                        await fs.promises.unlink(segPath);
                    }
                } else {
                    const tmpPath = `${segPath}.compact.tmp`;
                    await fs.promises.writeFile(tmpPath, keptLines.join('\n') + '\n', 'utf8');
                    await fs.promises.rename(tmpPath, segPath);
                }
            } catch {}
        }
    }

    public async stop(): Promise<void> {
        if (!this.enableWal) return;

        if (this.commitTimer) {
            clearTimeout(this.commitTimer);
            this.commitTimer = null;
            try { await this.ptrTracker?.commitLsn(this.lastCommittedLsn); } catch {}
        }

        if (this.compactTimer) {
            clearTimeout(this.compactTimer);
            this.compactTimer = null;
        }

        // 进行最终压缩并排空队列
        try {
            await this.writeMutex.runExclusive(async () => {
                await this.compactWalSegments();
            });
        } catch {}

        this.ptrTracker?.stop();
    }

    private async scanUncommitted(): Promise<WALRecoveredEntry[]> {
        const committedLsn = this.ptrTracker.getCommittedLsn();
        const segEntries = new Map<number, WALRecoveredEntry[]>();
        const deletedLsns = new Set<number>();
        
        const files = await fs.promises.readdir(this.walDir);
        const segNums = files
            .filter(f => f.startsWith('log1_') && f.endsWith('.wal'))
            .map(f => parseInt(f.split('_')[1]!.split('.')[0]!, 10))
            .sort((a, b) => a - b);

        for (const seg of segNums) {
            const segPath = path.join(this.walDir, `log1_${seg.toString().padStart(6, '0')}.wal`);
            const entries: WALRecoveredEntry[] = [];
            try {
                const content = await fs.promises.readFile(segPath, 'utf8');
                for (const line of content.split('\n')) {
                    if (!line) continue;
                    if (line.startsWith('DEL|')) {
                        const lsn = parseInt(line.substring(4), 10);
                        if (!isNaN(lsn)) deletedLsns.add(lsn);
                    } else {
                        const entry = this.parseRecord(line);
                        if (entry && entry.lsn > committedLsn) entries.push(entry);
                    }
                }
            } catch {}
            segEntries.set(seg, entries);
        }

        const uncommitted: WALRecoveredEntry[] = [];
        for (const entries of segEntries.values()) {
            for (const entry of entries) {
                if (!deletedLsns.has(entry.lsn)) uncommitted.push(entry);
            }
        }
        return uncommitted;
    }

    private parseRecord(line: string): WALRecoveredEntry | null {
        try {
            const parts = line.split('|');
            if (parts.length < 4) return null;
            const lsn = parseInt(parts[0]!, 10);
            const checksum = parts[1]!;
            const payloadLen = parseInt(parts[2]!, 10);
            const payload = parts.slice(3).join('|');
            if (isNaN(lsn) || isNaN(payloadLen)) return null;

            const actualChecksum = crypto.createHash('md5').update(payload).digest('hex').substring(0, 8);
            if (actualChecksum !== checksum) return null;

            const dict = JSON.parse(payload);
            return { lsn, priority: dict.priority ?? 0, payload };
        } catch { return null; }
    }

    private async cleanupOrphanedTmpFiles(): Promise<void> {
        try {
            const files = await fs.promises.readdir(this.walDir);
            for (const f of files) {
                if (f.endsWith('.tmp')) await fs.promises.unlink(path.join(this.walDir, f)).catch(() => {});
            }
        } catch {}
    }
}
