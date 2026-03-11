import { join } from 'path';

/**
 * PreferenceMerger - 偏好合并器
 *
 * 负责智能合并新旧偏好，处理冲突和去重
 */
export class PreferenceMerger {
    private llmProvider: any;
    private refiningPath: string;

    constructor(llmProvider: any, basePath: string = '.aethelum') {
        this.llmProvider = llmProvider;
        this.refiningPath = join(basePath, 'refining.md');
    }

    /**
     * 合并新偏好并更新文件
     */
    async mergeAndUpdate(newPreferences: string[]): Promise<void> {
        const existing = await this.loadExisting();
        const merged = await this.smartMerge(existing, newPreferences);
        await this.save(merged);
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
        const dir = this.refiningPath.split('/').slice(0, -1).join('/');
        if (!await Bun.file(dir).exists()) {
            const { mkdir } = await import('fs/promises');
            await mkdir(dir, { recursive: true });
        }
        await Bun.write(this.refiningPath, content);
        console.log(`[PreferenceMerger] Updated refining.md`);
    }
}
