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
  actionIntent: string;
  sourceAgent?: string;
  inputSource?: string;
  content?: any;
  metadata?: Record<string, any>;
  priority?: MessagePriority;
  expiresAt?: number;
  messageId?: string;
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

    this.status = MessageStatus.CREATED;
    this.timestamp = Date.now();
    this.routingHistory = [this.sourceAgent];
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
   * 使用统一验证器校验消息内容
   */
  public async validate(validator: UnifiedValidator): Promise<ValidationResult[]> {
    return await validator.validate(this.toDict());
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
      routingHistory: this.routingHistory
    };
  }
}
