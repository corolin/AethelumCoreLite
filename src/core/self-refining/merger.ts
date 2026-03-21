import { join, dirname } from 'path';
import type { LLMProvider } from '../../types/index.js';

/**
 * PreferenceMerger - 偏好合并器
 *
 * 负责智能合并新旧偏好，处理冲突和去重
 *
 * 内置内存级互斥锁，防止并发 mergeAndUpdate 导致丢失更新（Lost Update）。
 * 当多个 SelfRefiningWorker 同时触发合并时，请求会排队串行执行，
 * 确保每次"读取 → LLM 融合 → 写入"事务完整且不重叠。
 */
export class PreferenceMerger {
    private llmProvider: LLMProvider;
    private refiningPath: string;
    private mutex: Promise<void> = Promise.resolve();

    constructor(llmProvider: LLMProvider, basePath: string = '.aethelum') {
        this.llmProvider = llmProvider;
        this.refiningPath = join(basePath, 'refining.md');
    }

    /**
     * 合并新偏好并更新文件（互斥执行，防止并发丢失更新）
     */
    async mergeAndUpdate(newPreferences: string[]): Promise<void> {
        // 互斥排队：等前一次 mergeAndUpdate 完成后再执行
        const previous = this.mutex;
        let release: () => void;
        this.mutex = new Promise<void>((resolve) => { release = resolve; });

        await previous;
        try {
            const existing = await this.loadExisting();
            const merged = await this.smartMerge(existing, newPreferences);
            await this.save(merged);
        } finally {
            release!();
        }
    }

    private async loadExisting(): Promise<string | null> {
        try {
            return await Bun.file(this.refiningPath).text();
        } catch {
            return null;
        }
    }

    private async smartMerge(existing: string | null, newPrefs: string[]): Promise<string> {
        const existingText = existing || '（现有配置为空）';
        const newPrefsText = newPrefs.map(p => `- ${p}`).join('\n');

        const mergePrompt = `${existingText}

新提取的用户偏好：
${newPrefsText}

请合并以上内容，输出完整的 Markdown 配置文件。
要求：
1. 保留旧配置中仍然有效的规则
2. 添加新偏好
3. 新旧冲突时以新为准
4. 使用清晰的分类结构（如：沟通风格、禁忌事项、交互偏好等）
5. 只输出 Markdown，无其他文字`;

        try {
            const response = await this.llmProvider.chat([
                {
                    role: 'system',
                    content: '你是一个配置文件合并助手。输出标准的 Markdown 格式。'
                },
                {
                    role: 'user',
                    content: mergePrompt
                }
            ], {
                maxTokens: 1000,
                temperature: 0.3
            });

            return response.choices?.[0]?.message?.content || response.content || '';
        } catch (error) {
            console.error('[PreferenceMerger] LLM merge failed:', error);
            // 失败时返回简单合并的结果
            return existing || newPrefsText;
        }
    }

    private async save(content: string): Promise<void> {
        const dir = dirname(this.refiningPath);
        const { mkdir } = await import('fs/promises');
        await mkdir(dir, { recursive: true });
        await Bun.write(this.refiningPath, content);
        console.log(`[PreferenceMerger] Updated refining.md`);
    }
}
