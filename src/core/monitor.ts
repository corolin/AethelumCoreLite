import { AsyncAxonWorker, WorkerState } from './worker.js';

export interface WorkerMetrics {
    workerId: string;
    state: WorkerState;
    processedCount: number;
    errorCount: number;
    lastActiveTime: number;
    healthScore: number; // 0-100
    isTimedOut: boolean; // 是否超时未响应
}

export interface MonitorConfig {
    checkIntervalMs: number;
    errorThreshold: number; // 连续错误多少次触发挂起
    timeoutMs: number; // 空闲或无响应时间(普通)
    heartbeatTimeoutMs: number; // 任务处理中无心跳超时(死锁判定)
    hardExecutionTimeoutMs: number; // 单个任务绝对超时阈值
    autoRecovery: boolean; // 是否自动拉起
    recoveryDelayMs: number; // 熔断后多久尝试恢复
}

/**
 * 等比复刻 Python 版本的 WorkerMonitor
 * 没有复杂的全局锁，使用 Bun 的事件轮询（setInterval）实现纯净扫描
 */
export class AsyncWorkerMonitor {
    private workers: Map<string, AsyncAxonWorker> = new Map();
    private metrics: Map<string, WorkerMetrics> = new Map();
    private config: MonitorConfig;
    private intervalId?: NodeJS.Timeout | undefined;

    // 记录连续报错次数
    private consecutiveErrors: Map<string, number> = new Map();

    // 防止 checkHealth 重叠执行
    private _isChecking: boolean = false;

    // 追踪恢复定时器，用于关闭时取消
    private recoveryTimeouts: Set<NodeJS.Timeout> = new Set();

    constructor(config?: Partial<MonitorConfig>) {
        this.config = {
            checkIntervalMs: 5000,
            errorThreshold: 3,
            timeoutMs: 30000, // 30秒无响应(常规)
            heartbeatTimeoutMs: 30000, // 此时间内必须有心跳
            hardExecutionTimeoutMs: 300000, // 5分钟硬超时
            autoRecovery: true,
            recoveryDelayMs: 10000, // 给外部 10 秒时间修复
            ...config
        };
    }

    public registerWorker(worker: AsyncAxonWorker): void {
        const id = worker.id;
        this.workers.set(id, worker);

        // 初始化健康状态
        this.metrics.set(id, {
            workerId: id,
            state: worker.state,
            // 与 Worker 当前计数对齐；checkHealth 每轮仍会同步 worker.getProcessedCount()
            processedCount: worker.getProcessedCount(),
            errorCount: 0,
            lastActiveTime: Date.now(),
            healthScore: 100,
            isTimedOut: false
        });
        this.consecutiveErrors.set(id, 0);
    }

    public start(): void {
        if (this.intervalId) return;
        console.log(`[Monitor] 启动监控守护进程，扫描间隔: ${this.config.checkIntervalMs}ms`);

        this.intervalId = setInterval(() => {
            if (this._isChecking) return; // 跳过重叠执行
            this._isChecking = true;
            this.checkHealth().finally(() => {
                this._isChecking = false;
            });
        }, this.config.checkIntervalMs);
    }

    public stop(): void {
        // 取消所有待执行的恢复定时器
        for (const timeoutId of this.recoveryTimeouts) {
            clearTimeout(timeoutId);
        }
        this.recoveryTimeouts.clear();

        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = undefined;
            console.log(`[Monitor] 监控守护进程已停止`);
        }
    }

    // ============== 核心轮询与判定逻辑 ==============

    private async checkHealth(): Promise<void> {
        const now = Date.now();

        for (const [id, worker] of this.workers.entries()) {
            const metric = this.metrics.get(id);
            if (!metric) continue;

            const currentState = worker.state;
            let score = metric.healthScore;

            // 1. 同步状态 (实际应用中，Worker内部执行完hook后应该主动汇报，这里通过访问器或外部状态同步)
            // 在本复刻版，我们给 Worker 增加 public 的 getErrorCount 等接口
            const currentErrors = worker.getInternalErrorCount();
            const lastActive = worker.getLastActiveTime();
            metric.processedCount = worker.getProcessedCount();

            // 判断有没有新增错误
            if (currentErrors > metric.errorCount) {
                const diff = currentErrors - metric.errorCount;
                const currentConsecutive = (this.consecutiveErrors.get(id) || 0) + diff;
                this.consecutiveErrors.set(id, currentConsecutive);
                metric.errorCount = currentErrors;

                // 扣除健康分
                score = Math.max(0, score - (diff * 20));
            } else if (currentState === WorkerState.RUNNING) {
                // 健康恢复
                this.consecutiveErrors.set(id, 0);
                score = Math.min(100, score + 5);
            }

            // 2. 超时判定 (假死与死锁)
            const isProcessing = worker.getIsProcessing();
            let isTimeoutDetected = false;

            if (currentState === WorkerState.RUNNING) {
                if (isProcessing) {
                    // 正在干活：检查是否有心跳续命，或是否触及硬上限
                    const noHeartbeatDuration = now - worker.lastHeartbeatTime;
                    const totalProcessDuration = now - worker.processingStartTime;
                    
                    if (noHeartbeatDuration > this.config.heartbeatTimeoutMs || 
                        totalProcessDuration > this.config.hardExecutionTimeoutMs) {
                        isTimeoutDetected = true;
                        console.warn(`[Monitor🚨] 死锁诊断: Worker ${id} 任务卡死。未心跳: ${noHeartbeatDuration}ms, 总耗时: ${totalProcessDuration}ms`);
                    }
                } else {
                    // 空闲状态：虽然没有干活，但也要防范死循环吃光事件循环导致的假空闲
                    if (now - lastActive > this.config.timeoutMs) {
                        isTimeoutDetected = true;
                        console.warn(`[Monitor🚨] 假死诊断: Worker ${id} 超过 ${this.config.timeoutMs}ms 未响应事件。`);
                    }
                }
            }

            if (isTimeoutDetected) {
                if (!metric.isTimedOut) {
                    metric.isTimedOut = true;
                    score = Math.max(0, score - 50);
                }
            } else {
                metric.isTimedOut = false; // 恢复正常
            }

            metric.healthScore = score;
            metric.state = currentState;

            // 3. 执行干预策略 (熔断隔离)
            const consecutiveErr = this.consecutiveErrors.get(id) || 0;
            if (consecutiveErr >= this.config.errorThreshold || score <= 20) {
                if (currentState === WorkerState.RUNNING) {
                    await this.triggerCircuitBreaker(worker, consecutiveErr, score);
                }
            }
        }
    }

    private async triggerCircuitBreaker(worker: AsyncAxonWorker, errCount: number, score: number): Promise<void> {
        console.error(`[CircuitBreaker💥] Worker ${worker.id} 指标严重恶化 (连续错误: ${errCount}, 健康分: ${score})`);
        console.log(`[CircuitBreaker] 正在强制挂起 Worker ${worker.id} 避免污染队列...`);

        // 通过 Worker 提供的方法设置错误状态（熔断隔离）
        worker.setErrorState();

        if (this.config.autoRecovery) {
            this.scheduleRecovery(worker);
        }
    }

    private scheduleRecovery(worker: AsyncAxonWorker): void {
        console.log(`[AutoRecovery🩺] 已为 Worker ${worker.id} 排期 ${this.config.recoveryDelayMs}ms 后自动启动恢复程序。`);

        const timeoutId = setTimeout(() => {
            this.recoveryTimeouts.delete(timeoutId); // 已触发，从追踪中移除

            console.log(`[AutoRecovery🩺] 尝试重启 Worker ${worker.id} ...`);

            // 重置 Monitor 侧计量
            this.consecutiveErrors.set(worker.id, 0);
            if (this.metrics.has(worker.id)) {
                const metric = this.metrics.get(worker.id)!;
                metric.healthScore = 80; // 恢复期给 80 分
                metric.errorCount = 0; // 同步 monitor 侧的错误计数
            }

            // 重置 Worker 侧的内部错误计数（防止立即重新熔断）
            worker.resetInternalErrorCount();

            // 重新推入运行态
            worker.start().catch((err) => {
                console.error(`[AutoRecovery🩺] Worker ${worker.id} 复苏失败:`, err);
            });

        }, this.config.recoveryDelayMs);

        this.recoveryTimeouts.add(timeoutId);
    }

    public getGlobalMetrics(): Record<string, WorkerMetrics> {
        const res: Record<string, WorkerMetrics> = {};
        for (const [id, metric] of this.metrics.entries()) {
            res[id] = { ...metric };
        }
        return res;
    }

    /**
     * 获取当前超时的 Worker 列表
     * @returns 超时的 Worker ID 数组
     */
    public getTimedOutWorkers(): string[] {
        const timedOutWorkers: string[] = [];
        for (const [id, metric] of this.metrics.entries()) {
            if (metric.isTimedOut) {
                timedOutWorkers.push(id);
            }
        }
        return timedOutWorkers;
    }

    /**
     * 检查是否有任何 Worker 超时
     * @returns 是否有超时的 Worker
     */
    public hasTimedOutWorkers(): boolean {
        return this.getTimedOutWorkers().length > 0;
    }
}
