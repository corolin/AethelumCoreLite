import { v7 as uuidv7 } from 'uuid';
import { UnifiedValidator, ValidationResult } from '../utils/unified_validator.js';

export enum MessagePriority {
  CRITICAL = 0,
  HIGH = 1,
  NORMAL = 2,
  LOW = 3,
  BACKGROUND = 4
}

export enum MessageStatus {
  CREATED = 'created',
  QUEUED = 'queued',
  PROCESSING = 'processing',
  COMPLETED = 'completed',
  FAILED = 'failed',
  EXPIRED = 'expired',
  CANCELLED = 'cancelled'
}

export interface NeuralImpulseOptions {
  sessionId?: string;
  /** 路由意图 / 目标队列标识 */
  actionIntent: string;
  /** 当前处理该脉冲的逻辑 Agent 名 */
  sourceAgent?: string;
  /** 外部输入来源标签（如 API、CLI） */
  inputSource?: string;
  content?: any;
  /** 扩展元数据（含 wal_lsn、current_queue 等运行时字段） */
  metadata?: Record<string, any>;
  priority?: MessagePriority;
  /** 绝对过期时间（Unix 毫秒） */
  expiresAt?: number;
  messageId?: string;
  /**
   * 生命周期状态。`fromDict`/WAL 恢复时传入，避免被构造函数重置为 `CREATED`。
   */
  status?: MessageStatus;
  /**
   * 已走过的 Agent 链（调试用）。未传时默认为 `[sourceAgent]`。
   */
  routingHistory?: string[];
  /**
   * 每跳时间戳记录（node + 毫秒时间戳），用于精确追踪消费耗时。
   * 两两相减即得每跳耗时；`markHop()` 在运行时自动追加。
   */
  hopTimings?: HopTiming[];
  /**
   * 创建/序列化时间戳（毫秒）。恢复时传入以保持与 `toDict` 一致。
   */
  timestamp?: number;
}

/** 神经脉冲经过的每一跳（节点名 + 毫秒时间戳） */
export interface HopTiming {
  /** 节点标识：`队列Id:enqueue` / `队列Id:dequeue` / `workerId:process` / `队列Id:route` 等 */
  node: string;
  /** 毫秒时间戳 */
  ts: number;
}

/** 从序列化值安全还原 MessageStatus（未知值回退为 CREATED） */
function coerceMessageStatus(value: unknown): MessageStatus | undefined {
  if (typeof value !== 'string') return undefined;
  const allowed = Object.values(MessageStatus) as string[];
  return allowed.includes(value) ? (value as MessageStatus) : undefined;
}

/**
 * 神经脉冲 (NeuralImpulse)
 * 
 * 在 AethelumCoreLite 异步事件循环中流动的信息载体
 */
export class NeuralImpulse {
  public messageId: string;
  public sessionId: string;
  public actionIntent: string;
  public sourceAgent: string;
  public inputSource: string;
  public content: any;
  public metadata: Record<string, any>;
  public routingHistory: string[];
  /** 每跳时间戳记录，两两相减即得每跳耗时；运行时由 markHop() 追加 */
  public hopTimings: HopTiming[];
  public priority: MessagePriority;
  public expiresAt: number | undefined;
  public status: MessageStatus;
  public timestamp: number;

  constructor(options: NeuralImpulseOptions) {
    this.messageId = options.messageId ?? uuidv7();
    this.sessionId = options.sessionId ?? uuidv7();
    this.actionIntent = options.actionIntent;
    this.sourceAgent = options.sourceAgent ?? 'System';
    this.inputSource = options.inputSource ?? 'System';
    this.content = options.content ?? null;
    this.metadata = options.metadata ?? {};
    this.priority = options.priority !== undefined ? options.priority : MessagePriority.NORMAL;
    this.expiresAt = options.expiresAt;

    this.status = options.status !== undefined ? options.status : MessageStatus.CREATED;
    this.timestamp = options.timestamp !== undefined ? options.timestamp : Date.now();
    this.routingHistory =
      Array.isArray(options.routingHistory) && options.routingHistory.length > 0
        ? [...options.routingHistory]
        : [this.sourceAgent];
    this.hopTimings =
      Array.isArray(options.hopTimings) && options.hopTimings.length > 0
        ? options.hopTimings.map((h) => ({ node: h.node, ts: h.ts }))
        : [];
  }

  /**
   * 添加 Agent 到路由历史
   */
  public addToHistory(agentName: string): void {
    if (this.routingHistory[this.routingHistory.length - 1] !== agentName) {
      this.routingHistory.push(agentName);
    }
  }

  /**
   * 更新上游来源 Agent
   */
  public updateSource(newSource: string): void {
    this.sourceAgent = newSource;
    this.addToHistory(newSource);
  }

  /**
   * 检查消息是否过期
   */
  public isExpired(): boolean {
    if (this.expiresAt === undefined) return false;
    return Date.now() > this.expiresAt;
  }

  /**
   * 获取剩余生存时间（ms）
   */
  public getTTL(): number | null {
    if (this.expiresAt === undefined) return null;
    return Math.max(0, this.expiresAt - Date.now());
  }

  /**
   * 记录一次路由/处理跳的时间点。
   * 每跳的耗时 = 相邻两个 hop 时间戳之差；端到端耗时 = 末跳 - timestamp（出生时间）。
   */
  public markHop(node: string, ts: number = Date.now()): void {
    this.hopTimings.push({ node, ts });
  }

  /** 最近一跳的时间戳（无记录时返回 undefined） */
  public getLastHopTs(): number | undefined {
    const last = this.hopTimings[this.hopTimings.length - 1];
    return last?.ts;
  }

  /**
   * 端到端耗时（ms）：最近一跳时间 - 创建时间。
   * 无任何跳记录时回退为 `now - timestamp`。
   */
  public getEndToEndDuration(): number {
    const lastTs = this.getLastHopTs() ?? Date.now();
    return Math.max(0, lastTs - this.timestamp);
  }

  /**
   * 解析 UUIDv7 时间戳（毫秒精度，取自前 48 位时间戳位）。
   * 非 v7 或格式非法时返回 null。
   */
  public static parseUuidV7Timestamp(messageId: string): number | null {
    const hex = messageId.replace(/-/g, '');
    if (hex.length < 14) return null;
    // v7 版本位固定为 7（第 13 个 hex 字符的高 4 位）
    if (hex[12] !== '7') return null;
    const tsHex = hex.slice(0, 12);
    const ts = parseInt(tsHex, 16);
    if (isNaN(ts) || ts <= 0) return null;
    return ts;
  }

  /**
   * 使用统一验证器校验消息内容
   */
  public async validate(validator: UnifiedValidator): Promise<ValidationResult[]> {
    return await validator.validate(this.toDict());
  }

  /**
   * 从纯对象结构还原（用于 WAL 崩溃恢复）
   */
  public static fromDict(dict: Record<string, any>): NeuralImpulse {
    const status = coerceMessageStatus(dict.status);
    return new NeuralImpulse({
      messageId: dict.messageId,
      sessionId: dict.sessionId,
      actionIntent: dict.actionIntent,
      sourceAgent: dict.sourceAgent,
      inputSource: dict.inputSource,
      content: dict.content,
      metadata: dict.metadata,
      priority: dict.priority,
      expiresAt: dict.expiresAt,
      ...(status !== undefined ? { status } : {}),
      ...(Array.isArray(dict.routingHistory) ? { routingHistory: dict.routingHistory as string[] } : {}),
      ...(Array.isArray(dict.hopTimings) ? { hopTimings: dict.hopTimings as HopTiming[] } : {}),
      ...(typeof dict.timestamp === 'number' ? { timestamp: dict.timestamp } : {}),
    });
  }

  /**
   * 导出为纯对象结构
   */
  public toDict(): Record<string, any> {
    return {
      messageId: this.messageId,
      sessionId: this.sessionId,
      actionIntent: this.actionIntent,
      sourceAgent: this.sourceAgent,
      inputSource: this.inputSource,
      content: this.content,
      metadata: this.metadata,
      priority: this.priority,
      expiresAt: this.expiresAt,
      status: this.status,
      timestamp: this.timestamp,
      routingHistory: this.routingHistory,
      hopTimings: this.hopTimings.map((h) => ({ node: h.node, ts: h.ts }))
    };
  }
}
