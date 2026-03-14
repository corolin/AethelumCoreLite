import fs from 'fs';
import path from 'path';
import crypto from 'crypto';

class AsyncMutex {
    private promise = Promise.resolve();
    
    async runExclusive<T>(fn: () => Promise<T>): Promise<T> {
        let resolve: () => void;
        const nextPromise = new Promise<void>(res => { resolve = res; });
        const priorPromise = this.promise;
        this.promise = priorPromise.then(() => nextPromise);

        try {
            await priorPromise;
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
        // 利用 Node fs 原子重命名写入模拟 mmap 快照
        const tmpPath = `${this.ptrPath}.tmp`;
        await fs.promises.writeFile(tmpPath, lsn.toString(), 'utf8');
        await fs.promises.rename(tmpPath, this.ptrPath);
    }

    public stop(): void {
        console.log(`[WAL Tracker] 停止追踪，最后提交位点: ${this.committedLsn}`);
    }
}

export class ImprovedWALWriter {
    private queueId: string;
    private walDir: string;
    private enableWal: boolean;

    private ptrTracker!: WALPtrTracker;
    private lsnAllocator!: LSNAllocator;

    private currentSegmentPath!: string;
    private currentSegmentNum: number = 0;
    private maxSegmentSize: number;

    // 并发写入保护锁
    private writeMutex = new AsyncMutex();
    
    // Log2 批量防抖位点确认
    private lastCommittedLsn: number = 0;
    private commitTimer: NodeJS.Timeout | null = null;

    constructor(queueId: string, walDir: string = "wal_data_v2", enableWal: boolean = true, maxSegmentSize: number = 100 * 1024 * 1024) {
        this.queueId = queueId;
        this.walDir = path.join(process.cwd(), walDir, queueId);
        this.enableWal = enableWal;
        this.maxSegmentSize = maxSegmentSize;
    }

    public async start(): Promise<void> {
        if (!this.enableWal) return;

        await fs.promises.mkdir(this.walDir, { recursive: true });

        this.ptrTracker = new WALPtrTracker(path.join(this.walDir, 'tracker.ptr'));
        await this.ptrTracker.start();

        // 寻找最大的段号，用于初始化 Segment 和 LSN
        const files = (await fs.promises.readdir(this.walDir)).filter(f => f.startsWith('log1_') && f.endsWith('.wal'));
        let maxLsn = this.ptrTracker.getCommittedLsn();

        if (files.length > 0) {
            const segNums = files.map(f => parseInt(f.split('_')[1]!.split('.')[0]!, 10)).sort((a, b) => a - b);
            this.currentSegmentNum = segNums[segNums.length - 1]!;
        } else {
            this.currentSegmentNum = 0;
        }

        this.currentSegmentPath = path.join(this.walDir, `log1_${this.currentSegmentNum.toString().padStart(6, '0')}.wal`);
        this.lsnAllocator = new LSNAllocator(maxLsn + 1);

        console.log(`[WAL Writer ${this.queueId}] 启动成功，当前 LSN: ${this.lsnAllocator.getCurrentLsn()}，段号: ${this.currentSegmentNum}`);
    }

    public async writeLog1(messageId: string, priority: number, data: Record<string, any>): Promise<number | null> {
        if (!this.enableWal) return null;
        // Guard against calls before start() has completed
        if (!this.lsnAllocator) return null;

        return await this.writeMutex.runExclusive(async () => {
            const lsn = this.lsnAllocator.nextLsn();
            const payload = JSON.stringify(data);

            // 生成 checksum (简单 hash)
            const checksum = crypto.createHash('md5').update(payload).digest('hex').substring(0, 8);

            // 格式: LSN|CHECKSUM|PAYLOAD_LENGTH|PAYLOAD\n
            const record = `${lsn}|${checksum}|${Buffer.byteLength(payload)}|${payload}\n`;

            await fs.promises.appendFile(this.currentSegmentPath, record, 'utf8');

            // 检查文件大小并旋转
            const stats = await fs.promises.stat(this.currentSegmentPath);
            if (stats.size >= this.maxSegmentSize) {
                this.currentSegmentNum++;
                this.currentSegmentPath = path.join(this.walDir, `log1_${this.currentSegmentNum.toString().padStart(6, '0')}.wal`);
            }

            return lsn;
        });
    }

    public writeLog2(messageId: string, lsn?: number): void {
        if (!this.enableWal || lsn === undefined || lsn === null) return;
        // Guard against calls before start() has completed
        if (!this.ptrTracker) return;

        // 更新最后位点
        this.lastCommittedLsn = lsn;

        // 防抖或缓冲机制，基于时间或批量合并提交 LSN 到 ptr 文件
        if (!this.commitTimer) {
            this.commitTimer = setTimeout(() => {
                this.ptrTracker.commitLsn(this.lastCommittedLsn).catch(err => {
                    console.error(`[WAL Writer ${this.queueId}] 提交位点失败:`, err);
                });
                this.commitTimer = null;
            }, 500); // 性能与可靠性的绝佳平衡，500ms 写盘一次
        }
    }

    public async stop(): Promise<void> {
        if (!this.enableWal) return;
        // Flush any pending commit before stopping
        if (this.commitTimer !== null) {
            clearTimeout(this.commitTimer);
            this.commitTimer = null;
            try {
                await this.ptrTracker?.commitLsn(this.lastCommittedLsn);
            } catch (err) {
                console.error(`[WAL Writer ${this.queueId}] 停止时提交位点失败:`, err);
            }
        }
        this.ptrTracker?.stop();
    }
}
