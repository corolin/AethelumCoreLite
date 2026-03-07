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
    timeoutMs: number; // 多久不活跃算作异常挂机
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

    constructor(config?: Partial<MonitorConfig>) {
        this.config = {
            checkIntervalMs: 5000,
            errorThreshold: 3,
            timeoutMs: 30000, // 30秒无响应
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
            processedCount: 0, // 目前无法直接穿透进 Worker 读取私有，需要 Worker 暴露或注入，先给壳
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
            this.checkHealth();
        }, this.config.checkIntervalMs);
    }

    public stop(): void {
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
            const currentErrors = worker.getInternalErrorCount ? worker.getInternalErrorCount() : 0;
            const lastActive = worker.getLastActiveTime ? worker.getLastActiveTime() : now;

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

            // 2. 超时判定 (假死)
            if (currentState === WorkerState.RUNNING && (now - lastActive > this.config.timeoutMs)) {
                if (!metric.isTimedOut) {
                    console.warn(`[Monitor🚨] 警告: Worker ${id} 超过 ${this.config.timeoutMs}ms 未响应!`);
                    metric.isTimedOut = true;
                    score = Math.max(0, score - 50);
                }
            } else {
                // 恢复正常，清除超时标志
                metric.isTimedOut = false;
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

        // 修改 Worker 状态为故障隔离
        worker.state = WorkerState.ERROR;

        if (this.config.autoRecovery) {
            this.scheduleRecovery(worker);
        }
    }

    private scheduleRecovery(worker: AsyncAxonWorker): void {
        console.log(`[AutoRecovery🩺] 已为 Worker ${worker.id} 排期 ${this.config.recoveryDelayMs}ms 后自动启动恢复程序。`);

        // 利用 Bun/Node 原生的定时器即可完美充当 Python 里面的异步挂起恢复
        setTimeout(() => {
            console.log(`[AutoRecovery🩺] 尝试重启 Worker ${worker.id} ...`);

            // 重置计量
            this.consecutiveErrors.set(worker.id, 0);
            if (this.metrics.has(worker.id)) {
                this.metrics.get(worker.id)!.healthScore = 80; // 恢复期给 80 分
            }

            // 重新推入运行态
            worker.start().catch((err) => {
                console.error(`[AutoRecovery🩺] Worker ${worker.id} 复苏失败:`, err);
            });

        }, this.config.recoveryDelayMs);
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
