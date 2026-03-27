/**
 * WAL 写入语义说明
 *
 * - **writeDelete（tombstone）**：异步排队落盘（best-effort）。进程在 tombstone 持久化前崩溃时，
 *   该条 Log1 可能在下次启动被再次恢复并投递（at-least-once 语义下的重复），非数据丢失。
 * - **优雅退出**：`stop()` 会排空写入互斥队列，尽量让 pending 的 tombstone 落盘；仍不保证内核/磁盘缓存已刷盘。
 * - **scanUncommitted 段压缩**：仅在 `start()` 内同步执行；当前设计无并发段旋转与扫描的竞争。
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
        // 使用唯一临时文件名避免并发实例间的 rename 竞态
        const tmpPath = `${this.ptrPath}.${crypto.randomBytes(4).toString('hex')}.tmp`;
        await fs.promises.writeFile(tmpPath, lsn.toString(), 'utf8');
        await fs.promises.rename(tmpPath, this.ptrPath);
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
    // DEL 之后的段压缩防抖：将已删除记录物理移出 WAL 文件
    private compactTimer: NodeJS.Timeout | null = null;
    private compactDebounceMs: number = 1000;

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

        this.ptrTracker = new WALPtrTracker(path.join(this.walDir, 'tracker.ptr'));
        await this.ptrTracker.start();

        // 寻找最大的段号，用于初始化 Segment 和 LSN
        const files = (await fs.promises.readdir(this.walDir)).filter(f => f.startsWith('log1_') && f.endsWith('.wal'));
        let maxLsn = this.ptrTracker.getCommittedLsn();

        if (files.length > 0) {
            const segNums = files.map(f => parseInt(f.split('_')[1]!.split('.')[0]!, 10)).sort((a, b) => a - b);
            this.currentSegmentNum = segNums[segNums.length - 1]!;
            // 关键修复：不能仅依赖 tracker.ptr（writeLog2 已弃用，ptr 可能长期不前进）
            // 需要从现存 WAL 段中恢复历史最大 LSN，避免重启后 LSN 回绕复用。
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

    /**
     * 从现存段文件中扫描历史最大 LSN。
     * 仅解析 Log1 记录行（跳过 DEL tombstone 行）。
     */
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
            } catch {
                // 段文件不存在或不可读时跳过
            }
        }

        return maxLsn;
    }

    public async writeLog1(messageId: string, priority: number, data: Record<string, any>): Promise<number | null> {
        if (!this.enableWal) return null;
        // Guard against calls before start() has completed
        if (!this.lsnAllocator) {
            throw new Error(`[WAL Writer ${this.queueId}] writeLog1() called before start() has completed`);
        }

        return await this.writeMutex.runExclusive(async () => {
            const allocator = this.lsnAllocator!;
            const lsn = allocator.nextLsn();
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

    /**
     * 确认移交成功：更新 LSN 位点（防抖 500ms 批量提交）
     *
     * @deprecated 新路径请用 {@link writeDelete}（按 LSN 精确 tombstone）。本方法保留用于：
     * 旧版 `tracker.ptr` 单调位点语义、既有测试与外部调用，避免破坏向后兼容。
     */
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
            }, 500).unref(); // 不阻止进程优雅退出
        }
    }

    /**
     * 删除 WAL 记录：消息移交/过期后，向 WAL 写入 tombstone 标记
     * 格式: DEL|{lsn}
     * 崩溃恢复时被标记的记录不会重放；旧段文件在全量删除后会被自动清理
     *
     * **Best-effort**：通过互斥队列异步 `appendFile`，不阻塞调用方。若在 tombstone 落盘前进程崩溃，
     * 重启后对应 Log1 可能再次被恢复（与 at-least-once 一致）。需要更强持久化时需配合 `stop()` 排空或 OS/fsync 策略。
     */
    public writeDelete(lsn: number): void {
        if (!this.enableWal || !this.lsnAllocator) return;

        // 异步写入，不阻塞调用方；使用 writeMutex 避免与 Log1 并发写入交叉
        this.writeMutex.runExclusive(async () => {
            const record = `DEL|${lsn}\n`;
            await fs.promises.appendFile(this.currentSegmentPath, record, 'utf8');
        }).catch(err => {
            console.error(`[WAL Writer ${this.queueId}] 写入删除标记失败 LSN ${lsn}:`, err);
        });

        // 触发防抖压缩：把已 tombstone 的记录物理从段文件移除
        this.scheduleCompaction();
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
        if (this.compactTimer !== null) {
            clearTimeout(this.compactTimer);
            this.compactTimer = null;
        }
        // ① 先排空互斥队列，确保所有 pending 的 writeDelete 都落盘
        try {
            await this.writeMutex.runExclusive(async () => {});
        } catch (err) {
            console.error(`[WAL Writer ${this.queueId}] 停止时排空写入队列失败:`, err);
        }
        // ② 再做最终压缩（此时所有 DEL 标记已在磁盘上，压缩可以正确移除已删除的 Log1 行）
        try {
            await this.writeMutex.runExclusive(async () => {
                await this.compactWalSegments();
            });
        } catch (err) {
            console.error(`[WAL Writer ${this.queueId}] 停止时压缩 WAL 失败:`, err);
        }
        this.ptrTracker?.stop();
    }

    // ============== 崩溃恢复扫描 ==============

    /**
     * 扫描所有 WAL 段文件中未提交的条目
     *
     * 两阶段处理：
     * 1. 收集所有 Log1 条目与 DEL tombstone；
     * 2. 过滤掉 tombstone 标记的条目，同时删除已全量处理的旧段文件。
     *
     * ptrTracker 的 committedLsn 作为快速前向跳过的辅助优化（向后兼容），
     * tombstone 机制是精确的逐条删除依据，可正确处理乱序移交场景。
     */
    private async scanUncommitted(): Promise<WALRecoveredEntry[]> {
        const committedLsn = this.ptrTracker.getCommittedLsn();

        // segEntries[seg] = 该段的所有 Log1 条目
        const segEntries = new Map<number, WALRecoveredEntry[]>();
        // 所有已标记删除的 LSN（来自任意段的 DEL 记录）
        const deletedLsns = new Set<number>();

        for (let seg = 0; seg <= this.currentSegmentNum; seg++) {
            const segPath = path.join(this.walDir, `log1_${seg.toString().padStart(6, '0')}.wal`);
            const entries: WALRecoveredEntry[] = [];
            try {
                const content = await fs.promises.readFile(segPath, 'utf8');
                for (const line of content.split('\n')) {
                    if (!line) continue;
                    if (line.startsWith('DEL|')) {
                        // tombstone 记录：DEL|{lsn}
                        const delLsn = parseInt(line.substring(4), 10);
                        if (!isNaN(delLsn)) deletedLsns.add(delLsn);
                    } else {
                        const entry = this.parseRecord(line);
                        // committedLsn 快速跳过旧条目（向后兼容优化）
                        if (entry && entry.lsn > committedLsn) {
                            entries.push(entry);
                        }
                    }
                }
            } catch {
                // 段文件不存在则跳过
            }
            segEntries.set(seg, entries);
        }

        // 压缩：删除非当前段中所有 Log1 条目均已被 tombstone 的旧段文件
        // 边界说明：本方法仅在 start() 中单次调用；段旋转只发生在运行期 writeLog1/writeDelete，
        // 与启动期扫描无并发，故不会出现「扫描中途新段被创建却被误删」的竞态。若未来改为后台压缩，需加锁或快照段列表。
        for (const [seg, entries] of segEntries.entries()) {
            if (seg === this.currentSegmentNum) continue;
            const allDeleted = entries.length === 0 || entries.every(e => deletedLsns.has(e.lsn));
            if (allDeleted) {
                const segPath = path.join(this.walDir, `log1_${seg.toString().padStart(6, '0')}.wal`);
                try {
                    await fs.promises.unlink(segPath);
                    console.log(`[WAL Writer ${this.queueId}] 段文件已压缩清理: seg ${seg}`);
                } catch {
                    // 文件已被其他进程清理，忽略
                }
            }
        }

        // 收集所有未被 tombstone 标记的待恢复条目
        const uncommitted: WALRecoveredEntry[] = [];
        for (const entries of segEntries.values()) {
            for (const entry of entries) {
                if (!deletedLsns.has(entry.lsn)) {
                    uncommitted.push(entry);
                }
            }
        }

        return uncommitted;
    }

    /**
     * 解析单条 WAL 记录
     * 格式: LSN|CHECKSUM|PAYLOAD_LENGTH|PAYLOAD
     * 注意: JSON payload 可能包含 '|'，因此基于前 3 个分隔符定位
     */
    private parseRecord(line: string): WALRecoveredEntry | null {
        const firstSep = line.indexOf('|');
        if (firstSep === -1) return null;
        const secondSep = line.indexOf('|', firstSep + 1);
        if (secondSep === -1) return null;
        const thirdSep = line.indexOf('|', secondSep + 1);
        if (thirdSep === -1) return null;

        const lsn = parseInt(line.substring(0, firstSep), 10);
        if (isNaN(lsn)) return null;

        const checksum = line.substring(firstSep + 1, secondSep);
        const payloadLen = parseInt(line.substring(secondSep + 1, thirdSep), 10);
        const payload = line.substring(thirdSep + 1);

        if (Buffer.byteLength(payload, 'utf8') !== payloadLen) {
            console.warn(`[WAL ${this.queueId}] 载荷长度不匹配: LSN ${lsn}, expected ${payloadLen}, got ${Buffer.byteLength(payload, 'utf8')}`);
            return null;
        }

        const actualChecksum = crypto.createHash('md5').update(payload).digest('hex').substring(0, 8);
        if (actualChecksum !== checksum) {
            console.warn(`[WAL ${this.queueId}] 校验和不匹配: LSN ${lsn}`);
            return null;
        }

        // 从 payload JSON 中提取 priority
        let priority = 0;
        try {
            const dict = JSON.parse(payload);
            priority = dict.priority ?? 0;
        } catch { /* 使用默认值 */ }

        return { lsn, priority, payload };
    }

    /**
     * DEL 写入后的防抖压缩调度
     */
    private scheduleCompaction(): void {
        if (!this.enableWal) return;
        if (this.compactTimer !== null) {
            clearTimeout(this.compactTimer);
        }
        this.compactTimer = setTimeout(() => {
            this.writeMutex.runExclusive(async () => {
                await this.compactWalSegments();
            }).catch(err => {
                console.error(`[WAL Writer ${this.queueId}] 压缩 WAL 段失败:`, err);
            }).finally(() => {
                this.compactTimer = null;
            });
        }, this.compactDebounceMs).unref();
    }

    /**
     * 物理压缩 WAL 段：
     * - 删除所有 DEL 行
     * - 删除已被 DEL 标记的 Log1 行
     * - 空旧段直接删除；当前段为空则保留空文件继续写
     */
    private async compactWalSegments(): Promise<void> {
        const segNums = (await fs.promises.readdir(this.walDir))
            .filter(f => f.startsWith('log1_') && f.endsWith('.wal'))
            .map(f => parseInt(f.split('_')[1]!.split('.')[0]!, 10))
            .filter(n => !isNaN(n))
            .sort((a, b) => a - b);

        if (segNums.length === 0) return;

        const deletedLsns = new Set<number>();
        const segLog1Lines = new Map<number, string[]>();

        // 第 1 遍：收集 DEL 集合 + 每段 Log1 原始行
        for (const seg of segNums) {
            const segPath = path.join(this.walDir, `log1_${seg.toString().padStart(6, '0')}.wal`);
            try {
                const content = await fs.promises.readFile(segPath, 'utf8');
                const lines = content.split('\n').filter(Boolean);
                const log1Lines: string[] = [];
                for (const line of lines) {
                    if (line.startsWith('DEL|')) {
                        const delLsn = parseInt(line.substring(4), 10);
                        if (!isNaN(delLsn)) deletedLsns.add(delLsn);
                        continue;
                    }
                    log1Lines.push(line);
                }
                segLog1Lines.set(seg, log1Lines);
            } catch {
                // 文件可能并发删除，忽略
            }
        }

        // 第 2 遍：按 DEL 集合重写段文件
        for (const seg of segNums) {
            const segPath = path.join(this.walDir, `log1_${seg.toString().padStart(6, '0')}.wal`);
            const log1Lines = segLog1Lines.get(seg) || [];
            const keptLines = log1Lines.filter(line => {
                const firstSep = line.indexOf('|');
                if (firstSep <= 0) return false;
                const lsn = parseInt(line.substring(0, firstSep), 10);
                if (isNaN(lsn)) return false;
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
                    await fs.promises.writeFile(tmpPath, `${keptLines.join('\n')}\n`, 'utf8');
                    await fs.promises.rename(tmpPath, segPath);
                }
            } catch {
                // 压缩失败保持原文件，不影响主流程
            }
        }
    }
}
