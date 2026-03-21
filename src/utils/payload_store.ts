import fs from 'fs';
import path from 'path';
import { v7 as uuidv7 } from 'uuid';

export interface PayloadReference {
    type: 'reference';
    uri: string;
}

// 统一负载存储接口
export interface IPayloadStore {
    /**
     * 将大段上下文/负载数据存入存储系统，并返回一个符合通信协议的 URI 引用。
     * URI 格式: NeuralImpulsePayload://{session_guid}/{conversation_guid}/{payload_guid}.md
     *
     * @param content 要存储的实际内容 (通常是大段 JSON 字符串或大段文本)
     * @param sessionId 当前会话的 GUID
     * @param conversationId 对话的 GUID (默认使用 'default' 或者您可以传入关联的对话 ID)
     * @returns PayloadReference 对象，包含可以存入 NeuralImpulse.content 的 URI
     */
    savePayload(content: string, sessionId: string, conversationId?: string): Promise<PayloadReference>;

    /**
     * 根据 NeuralImpulse 的 Payload 引用 URI，从存储系统异步读取完整的长程内容。
     *
     * @param uri NeuralImpulsePayload:// 协议的地址
     * @returns 读取到的内容字符串；如果 URI 不合法或记录不存在，则返回 null
     */
    loadPayload(uri: string): Promise<string | null>;

    /**
     * 判断一段由于可能是 content 的 object 是不是 Payload 引用
     */
    isPayloadReference(content: any): content is PayloadReference;
}

/**
 * 校验路径片段是否安全（仅允许 UUID、字母、数字、短横线、下划线、点号）
 */
function isSafePathSegment(segment: string): boolean {
    return /^[a-zA-Z0-9\-_.]+$/.test(segment);
}

/**
 * 校验最终解析路径是否在 baseDir 内（防止路径穿越）
 */
function isWithinBaseDir(resolvedPath: string, baseDir: string): boolean {
    // 确保两个路径都以路径分隔符结尾，避免 /baseDirFoo 匹配 /baseDir
    const normalized = resolvedPath.replace(/\\/g, '/');
    const normalizedBase = baseDir.replace(/\\/g, '/');
    return normalized.startsWith(normalizedBase + '/') || normalized === normalizedBase;
}

export class LocalPayloadStore implements IPayloadStore {
    private baseDir: string;

    constructor(baseDir: string = '.aethelum/payloads') {
        this.baseDir = path.resolve(process.cwd(), baseDir);

        // Ensure base directory exists
        fs.mkdirSync(this.baseDir, { recursive: true });
    }

    public async savePayload(
        content: string,
        sessionId: string,
        conversationId: string = 'default'
    ): Promise<PayloadReference> {
        // 安全校验路径片段
        if (!isSafePathSegment(sessionId)) {
            throw new Error(`[LocalPayloadStore] sessionId 包含非法字符: ${sessionId}`);
        }
        if (!isSafePathSegment(conversationId)) {
            throw new Error(`[LocalPayloadStore] conversationId 包含非法字符: ${conversationId}`);
        }

        const payloadGuid = uuidv7();
        const uri = `NeuralImpulsePayload://${sessionId}/${conversationId}/${payloadGuid}.md`;

        // 构建本地文件路径 (如: .aethelum/payloads/session_guid/conversation_guid/ )
        const fullDir = path.resolve(this.baseDir, sessionId, conversationId);

        // 路径穿越校验
        if (!isWithinBaseDir(fullDir, this.baseDir)) {
            throw new Error(`[LocalPayloadStore] 路径穿越攻击已阻止: ${fullDir}`);
        }

        // 确保目录存在
        await fs.promises.mkdir(fullDir, { recursive: true });

        // 将内容存入 .md 或 .json 等后缀对应的文件
        const filePath = path.join(fullDir, `${payloadGuid}.md`);
        await fs.promises.writeFile(filePath, content, 'utf-8');

        return {
            type: 'reference',
            uri
        };
    }

    public async loadPayload(uri: string): Promise<string | null> {
        const protocolHeader = 'NeuralImpulsePayload://';

        if (!uri.startsWith(protocolHeader)) {
            console.warn(`[LocalPayloadStore] 无效的 URI 协议头: ${uri}`);
            return null;
        }

        // 解析 URI: NeuralImpulsePayload://{session_guid}/{conversation_guid}/{payload_guid}.md
        const urlPath = uri.replace(protocolHeader, '');
        const urlParts = urlPath.split('/');

        // URI 应当包含 3 段: sessionId, conversationId, fileName
        if (urlParts.length !== 3) {
            console.warn(`[LocalPayloadStore] URI 格式解析失败 (未找到三段路径): ${uri}`);
            return null;
        }

        const [sessionId, conversationId, fileName] = urlParts;
        if (!sessionId || !conversationId || !fileName) return null;

        // 安全校验：拒绝包含路径分隔符或穿越字符的片段
        for (const segment of [sessionId, conversationId, fileName]) {
            if (!isSafePathSegment(segment)) {
                console.warn(`[LocalPayloadStore] URI 路径片段包含非法字符: ${segment}`);
                return null;
            }
        }

        const filePath = path.resolve(this.baseDir, sessionId, conversationId, fileName);

        // 路径穿越二次校验
        if (!isWithinBaseDir(filePath, this.baseDir)) {
            console.warn(`[LocalPayloadStore] 路径穿越攻击已阻止: ${filePath}`);
            return null;
        }

        try {
            // 验证文件存在性 (异步非阻塞)
            await fs.promises.access(filePath, fs.constants.R_OK);
            return await fs.promises.readFile(filePath, 'utf-8');
        } catch (err) {
            console.error(`[LocalPayloadStore] 无法读取负载文件: ${filePath}`, err);
            return null;
        }
    }

    public isPayloadReference(content: any): content is PayloadReference {
        return (
            content !== null &&
            typeof content === 'object' &&
            content.type === 'reference' &&
            typeof content.uri === 'string' &&
            content.uri.startsWith('NeuralImpulsePayload://')
        );
    }
}
