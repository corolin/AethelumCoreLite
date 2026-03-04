import fs from 'fs';
import path from 'path';
import crypto from 'crypto';

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

    public start(): void {
        if (!fs.existsSync(this.ptrPath)) {
            this.writeLsn(0);
        } else {
            const data = fs.readFileSync(this.ptrPath, 'utf8');
            this.committedLsn = parseInt(data, 10) || 0;
            console.log(`[WAL Tracker] 加载位点 LSN: ${this.committedLsn}`);
        }
    }

    public getCommittedLsn(): number {
        return this.committedLsn;
    }

    public commitLsn(lsn: number): void {
        this.committedLsn = lsn;
        this.writeLsn(lsn);
    }

    private writeLsn(lsn: number): void {
        // 利用 Node fs 原子重命名写入模拟 mmap 快照
        const tmpPath = `${this.ptrPath}.tmp`;
        fs.writeFileSync(tmpPath, lsn.toString(), 'utf8');
        fs.renameSync(tmpPath, this.ptrPath);
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

    constructor(queueId: string, walDir: string = "wal_data_v2", enableWal: boolean = true, maxSegmentSize: number = 100 * 1024 * 1024) {
        this.queueId = queueId;
        this.walDir = path.join(process.cwd(), walDir, queueId);
        this.enableWal = enableWal;
        this.maxSegmentSize = maxSegmentSize;

        if (this.enableWal) {
            fs.mkdirSync(this.walDir, { recursive: true });
        }
    }

    public start(): void {
        if (!this.enableWal) return;

        this.ptrTracker = new WALPtrTracker(path.join(this.walDir, 'tracker.ptr'));
        this.ptrTracker.start();

        // 寻找最大的段号，用于初始化 Segment 和 LSN
        const files = fs.readdirSync(this.walDir).filter(f => f.startsWith('log1_') && f.endsWith('.wal'));
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
    }

    public writeLog2(messageId: string, lsn?: number): void {
        if (!this.enableWal || lsn === undefined || lsn === null) return;

        // 提交位点
        this.ptrTracker.commitLsn(lsn);
    }

    public stop(): void {
        if (!this.enableWal) return;
        this.ptrTracker.stop();
    }
}
