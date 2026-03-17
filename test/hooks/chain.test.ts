import { describe, expect, test, beforeEach } from "bun:test";
import { AsyncHookChain, BaseAsyncHook } from "../../src/hooks/chain.js";
import { NeuralImpulse } from "../../src/core/message.js";
import { HookType } from "../../src/hooks/types.js";

class TestHook extends BaseAsyncHook {
    private fn: (impulse: NeuralImpulse) => Promise<NeuralImpulse | null>;
    constructor(name: string, type: HookType, priority: number = 0, timeoutMs: number = 0, fn?: (impulse: NeuralImpulse) => Promise<NeuralImpulse | null>) {
        super(name, type, priority, timeoutMs);
        this.fn = fn || (async (imp) => imp);
    }
    async executeAsync(impulse: NeuralImpulse): Promise<NeuralImpulse | null> {
        return await this.fn(impulse);
    }
}

describe("AsyncHookChain - Unit Tests", () => {
    let chain: AsyncHookChain;

    beforeEach(() => {
        chain = new AsyncHookChain("test_chain");
    });

    test("addHook() respects priority", () => {
        const hook1 = new TestHook("h1", HookType.PRE_PROCESS, 10);
        const hook2 = new TestHook("h2", HookType.PRE_PROCESS, 20);
        const hook3 = new TestHook("h3", HookType.PRE_PROCESS, 5);

        chain.addHook(hook1);
        chain.addHook(hook2);
        chain.addHook(hook3);

        const activeHooks = chain.getHooksByType(HookType.PRE_PROCESS);
        expect(activeHooks[0].name).toBe("h2");
        expect(activeHooks[1].name).toBe("h1");
        expect(activeHooks[2].name).toBe("h3");
    });

    test("removeHook() and clear()", () => {
        chain.addHook(new TestHook("h1", HookType.PRE_PROCESS));
        chain.addHook(new TestHook("h2", HookType.PRE_PROCESS));
        
        expect(chain.removeHook("h1")).toBe(true);
        expect(chain.getHooksByType(HookType.PRE_PROCESS).length).toBe(1);
        
        chain.clear();
        expect(chain.getHooksByType(HookType.PRE_PROCESS).length).toBe(0);
    });

    test("executeHooks() chain transformation", async () => {
        const h1 = new TestHook("h1", HookType.PRE_PROCESS, 10, 0, async (imp) => {
            imp.content = "step1";
            return imp;
        });
        const h2 = new TestHook("h2", HookType.PRE_PROCESS, 5, 0, async (imp) => {
            imp.content += "_step2";
            return imp;
        });

        chain.addHook(h1);
        chain.addHook(h2);

        const impulse = new NeuralImpulse({ actionIntent: "test", content: "init" });
        const result = await chain.executeHooks(impulse, HookType.PRE_PROCESS, {} as any);

        expect(result?.content).toBe("step1_step2");
    });

    test("executeHooks() intercept (return null)", async () => {
        const h1 = new TestHook("h1", HookType.PRE_PROCESS, 10, 0, async () => null);
        const h2 = new TestHook("h2", HookType.PRE_PROCESS, 5, 0, async (imp) => {
            imp.content = "should_not_run";
            return imp;
        });

        chain.addHook(h1);
        chain.addHook(h2);

        const impulse = new NeuralImpulse({ actionIntent: "test" });
        const result = await chain.executeHooks(impulse, HookType.PRE_PROCESS, {} as any);

        expect(result).toBeNull();
    });

    test("executeHooks() timeout", async () => {
        const slowHook = new TestHook("slow", HookType.PRE_PROCESS, 0, 100, async (imp) => {
            await new Promise(r => setTimeout(r, 200));
            return imp;
        });

        chain.addHook(slowHook);
        const impulse = new NeuralImpulse({ actionIntent: "test" });

        expect(chain.executeHooks(impulse, HookType.PRE_PROCESS, {} as any)).rejects.toThrow("Hook slow timeout");
    });

    test("BaseAsyncHook enable/disable", async () => {
        const hook = new TestHook("h", HookType.PRE_PROCESS);
        hook.disable();
        chain.addHook(hook);
        
        expect(chain.getHooksByType(HookType.PRE_PROCESS).length).toBe(0);
        
        hook.enable();
        expect(chain.getHooksByType(HookType.PRE_PROCESS).length).toBe(1);
    });
});
