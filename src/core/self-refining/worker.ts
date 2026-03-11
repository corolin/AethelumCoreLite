import { AsyncAxonWorker } from '../worker.js';
import { NeuralImpulse, MessagePriority } from '../message.js';
import { CoreLiteRouter } from '../router.js';
import { ConversationAnalyzer } from './analyzer.js';
import { PreferenceMerger } from './merger.js';

/**
 * SelfRefiningWorker - 自我反思工作器
 *
 * 功能：
 * 1. 接收包含对话历史的脉冲
 * 2. 调用轻量级 LLM 分析用户偏好/纠正
 * 3. 将提取结果存储到 refining.md
 */
export class SelfRefiningWorker extends AsyncAxonWorker {
    private analyzer: ConversationAnalyzer;
    private merger: PreferenceMerger;

    constructor(
        id: string,
        inputQueue: any,
        router: CoreLiteRouter,
        config: {
            llmProvider: any;
            reflectionPrompt?: string;
        }
    ) {
        super(id, inputQueue, router);
        this.analyzer = new ConversationAnalyzer(config.llmProvider, config.reflectionPrompt);
        this.merger = new PreferenceMerger(config.llmProvider);
    }

    protected async process(impulse: NeuralImpulse): Promise<void> {
        // 1. 检查触发来源
        const triggerSource = impulse.content?.trigger_source;
        const originalMessages = impulse.content?.original_messages || [];
        const compressionSummary = impulse.content?.compression_summary;

        // 只处理来自记忆压缩的触发
        if (triggerSource !== 'compression_complete' || originalMessages.length === 0) {
            await this.routeAndDone(impulse, 'Q_DONE');
            return;
        }

        console.log(`[SelfRefiningWorker] Processing ${originalMessages.length} messages from compression`);

        // 2. 分析压缩后的对话，提取偏好
        const extractedPreferences = await this.analyzer.extractPreferences({
            original_messages: originalMessages,
            compression_summary: compressionSummary
        });

        if (!extractedPreferences || extractedPreferences.length === 0) {
            console.log('[SelfRefiningWorker] No new preferences extracted');
            await this.routeAndDone(impulse, 'Q_DONE');
            return;
        }

        console.log(`[SelfRefiningWorker] Extracted ${extractedPreferences.length} new preferences:`);
        extractedPreferences.forEach((pref, i) => console.log(`  ${i + 1}. ${pref}`));

        // 3. 合并到 refining.md
        await this.merger.mergeAndUpdate(extractedPreferences);

        // 4. 完成
        await this.routeAndDone(impulse, 'Q_DONE');
    }
}
