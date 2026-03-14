import { CoreLiteRouter } from '../src/core/router.js';
import { AsyncSynapticQueue } from '../src/core/queue.js';
import { AsyncAxonWorker } from '../src/core/worker.js';
import { NeuralImpulse, MessagePriority } from '../src/core/message.js';
import { BaseAsyncHook } from '../src/hooks/chain.js';
import { HookType } from '../src/hooks/types.js';
import type { HookContext } from '../src/hooks/types.js';

// ==========================================
// 1. 各个业务 Hook 实现
// ==========================================

// 输入审计 Hook
class InputAuditHook extends BaseAsyncHook {
    constructor() {
        super('SecurityInputAuditor', HookType.PRE_PROCESS);
    }

    async executeAsync(impulse: NeuralImpulse, context: HookContext): Promise<NeuralImpulse | null> {

        // 简单的关键词审计
        if (typeof impulse.content === 'string' && impulse.content.includes('DROP TABLE')) {
            console.warn(`[InputAuditor] 发现恶意输入，拦截！`);
            return null;
        }

        impulse.metadata['audit_input_passed'] = true;

        // 手动将意图修改为下一步的业务处理队列
        impulse.actionIntent = 'Q_AUDITED_INPUT';
        return impulse;
    }
}

// 核心业务处理 Hook
class BusinessLogicHook extends BaseAsyncHook {
    constructor() {
        super('AIServiceHandler', HookType.PRE_PROCESS);
    }

    async executeAsync(impulse: NeuralImpulse, context: HookContext): Promise<NeuralImpulse | null> {
        // 模拟耗时的异步调用 (比如请求大模型)
        await new Promise(resolve => setTimeout(resolve, 800));

        // 生成响应
        impulse.content = `【AI响应】您好，您输入的内容是 "${impulse.content}"。处理完毕！`;

        // 设置下一个路由节点：根据之前的修正，业务处理完后必须去输出审计，然后再去 SINK
        impulse.actionIntent = 'Q_AUDIT_OUTPUT';
        return impulse;
    }
}

// 输出审计 Hook
class OutputAuditHook extends BaseAsyncHook {
    constructor() {
        super('SecurityOutputAuditor', HookType.PRE_PROCESS);
    }

    async executeAsync(impulse: NeuralImpulse, context: HookContext): Promise<NeuralImpulse | null> {
        // 确保没有泄漏敏感信息
        if (typeof impulse.content === 'string' && impulse.content.includes('PASSWORD')) {
            console.warn(`[OutputAuditor] 发现泄漏敏感信息，拦截！`);
            return null;
        }

        impulse.metadata['audit_output_passed'] = true;

        // 输出审计通过后，允许路由到最终 SINK
        impulse.actionIntent = 'Q_RESPONSE_SINK';
        return impulse;
    }
}

// SINK 最终响应分发 Hook
class ResponseSinkHook extends BaseAsyncHook {
    constructor() {
        super('FinalResponseSender', HookType.PRE_PROCESS);
    }

    async executeAsync(impulse: NeuralImpulse, context: HookContext): Promise<NeuralImpulse | null> {
        console.log(`\n========================================`);
        console.log(`[ResponseSink] 🎯 消息已抵达最终终点！`);
        console.log(`[ResponseSink] 完整路由路径: ${impulse.routingHistory.join(' -> ')}`);
        console.log(`[ResponseSink] 最终响应内容: ${impulse.content}`);
        console.log(`========================================\n`);

        impulse.actionIntent = 'Done';
        return impulse;
    }
}

// ==========================================
// 2. 主测试流程
// ==========================================

async function runDemo() {
    console.log('🚀 初始化 AethelumCoreLite 骨架...');
    const router = new CoreLiteRouter();

    // 1. 注册工作器
    // 实例化工作器之前需要实例化对应的队列
    const qInput = new AsyncSynapticQueue('Q_AUDIT_INPUT', 1000);
    const qBiz = new AsyncSynapticQueue('Q_AUDITED_INPUT', 1000);
    const qOutput = new AsyncSynapticQueue('Q_AUDIT_OUTPUT', 1000);
    const qSink = new AsyncSynapticQueue('Q_RESPONSE_SINK', 1000);

    router.registerQueue(qInput);
    router.registerQueue(qBiz);
    router.registerQueue(qOutput);
    router.registerQueue(qSink);

    const inputWorker = new AsyncAxonWorker('AuditInputWorker', qInput, router);
    const bizWorker = new AsyncAxonWorker('BusinessBIZWorker', qBiz, router);
    const outputWorker = new AsyncAxonWorker('AuditOutputWorker', qOutput, router);
    const sinkWorker = new AsyncAxonWorker('ResponseSinkWorker', qSink, router);

    router.registerWorker(inputWorker);
    router.registerWorker(bizWorker);
    router.registerWorker(outputWorker);
    router.registerWorker(sinkWorker);

    // 2. 将 Hook 绑定到他们的前置处理链
    inputWorker.getPreHooks().addHook(new InputAuditHook());
    bizWorker.getPreHooks().addHook(new BusinessLogicHook());
    outputWorker.getPreHooks().addHook(new OutputAuditHook());
    sinkWorker.getPreHooks().addHook(new ResponseSinkHook());

    // 3. 启动路由器激活所有工作器
    router.activate();

    // 4. 输入几条测试脉冲
    console.log('\n===== 发送测试消息 1: 正常流程 =====');
    await router.injectInput(new NeuralImpulse({
        sessionId: 'session-001',
        actionIntent: 'Q_AUDIT_INPUT', // 实际上 injectInput 也会强制覆盖
        content: '帮我写一份代码审核报告',
        priority: MessagePriority.NORMAL
    }));

    // 发送第二条，测试非法越权 (直接找SINK)。应该在路由器层被拦截。
    setTimeout(async () => {
        console.log('\n===== 发送测试消息 2: 非法越权尝试 =====');
        const maliciousImpulse = new NeuralImpulse({
            sessionId: 'session-malicious',
            actionIntent: 'Q_RESPONSE_SINK',
            sourceAgent: 'HackerBot',
            content: '我是黑客，我直接塞给 Sink'
        });
        await router.routeMessage(maliciousImpulse, 'Q_RESPONSE_SINK');
    }, 100);

    // 给系统一点时间跑完... 
    setTimeout(async () => {
        console.log('🛑 生成排队指标并准备关闭...');
        console.log('当前队列状态:', router.getQueueMetrics());
        await router.stop();
    }, 2500);
}

runDemo().catch(console.error);
