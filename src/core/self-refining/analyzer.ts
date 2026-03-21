import { join } from 'path';
import type { LLMProvider } from '../../types/index.js';

/**
 * ConversationAnalyzer - 对话分析器
 *
 * 负责分析压缩后的对话，提取用户的偏好和纠正信息
 */
export class ConversationAnalyzer {
    private llmProvider: LLMProvider;
    private refiningPath: string;

    constructor(llmProvider: LLMProvider, _customPrompt?: string) {
        this.llmProvider = llmProvider;
        this.refiningPath = join('.aethelum', 'refining.md');
    }

    /**
     * 从压缩数据中提取用户偏好
     * @param data 包含原始消息、压缩摘要的数据
     * @returns 偏好列表，如果没有则返回空数组
     */
    async extractPreferences(data: {
        original_messages: unknown[];
        compression_summary: string;
    }): Promise<string[]> {
        // 1. 读取现有的自我进化配置
        const existingRefining = await this.loadExistingRefining();

        // 2. 构建分析提示，包含三个维度的信息
        const analysisPrompt = this.buildAnalysisPrompt(
            data.compression_summary,
            existingRefining
        );

        try {
            const response = await this.llmProvider.chat([
                {
                    role: 'system',
                    content: '你是一个自我反思分析引擎。严格按照要求的 JSON 格式输出。'
                },
                {
                    role: 'user',
                    content: analysisPrompt
                }
            ], {
                maxTokens: 800,
                temperature: 0.3
            });

            const content = response.choices?.[0]?.message?.content || response.content || '';
            return this.parseResponse(content);
        } catch (error) {
            console.error('[ConversationAnalyzer] LLM call failed:', error);
            return [];
        }
    }

    /**
     * 加载现有的 refining.md
     */
    private async loadExistingRefining(): Promise<string | null> {
        try {
            return await Bun.file(this.refiningPath).text();
        } catch {
            return null;
        }
    }

    /**
     * 构建分析提示
     * 对比：压缩摘要 vs 现有进化配置
     */
    private buildAnalysisPrompt(
        compressionSummary: string,
        existingRefining: string | null
    ): string {
        const existingText = existingRefining
            ? `## 现有的自我进化配置（refining.md）：\n${existingRefining}\n\n`
            : `## 现有的自我进化配置：\n（空 - 尚无任何进化配置）\n\n`;

        return `${this.getDefaultPrompt()}

---

${existingText}

## 本次对话压缩摘要：

${compressionSummary}

---

请分析以上内容，输出 JSON 格式结果。`;
    }

    private parseResponse(content: string): string[] {
        try {
            // 用首尾大括号定位 JSON 对象，避免正则回溯导致的 ReDoS 风险
            const firstBrace = content.indexOf('{');
            const lastBrace = content.lastIndexOf('}');
            if (firstBrace === -1 || lastBrace === -1 || lastBrace < firstBrace) return [];

            const parsed = JSON.parse(content.slice(firstBrace, lastBrace + 1));
            if (parsed.has_new_preferences && parsed.preferences) {
                return parsed.preferences;
            }
            return [];
        } catch (error) {
            console.error('[ConversationAnalyzer] Failed to parse response:', error);
            return [];
        }
    }

    private getDefaultPrompt(): string {
        return `你是一个自我反思分析引擎。

# 任务
阅读"本次对话压缩摘要"和"现有的自我进化配置"，提取出**新的**用户偏好、要求或纠正信息。

# 分析原则
1. 只提取**全局性**的偏好（对整个对话风格、格式、内容的长期要求）
2. 忽略**临时性**的请求（如"帮我写个函数"这种一次性任务）
3. 如果压缩摘要中体现的用户偏好**已在现有配置中**，则不重复提取
4. 如果用户**改变**了之前的偏好（如从"详细解释"变为"简洁回答"），这是重要的变化，需要提取

# 返回格式（纯 JSON）
- 没有新偏好：{"has_new_preferences": false}
- 有新偏好：{"has_new_preferences": true, "preferences": ["规则1", "规则2", ...]}

只返回 JSON，不要其他内容。`;
    }
}
