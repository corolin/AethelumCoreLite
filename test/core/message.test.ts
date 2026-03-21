import { describe, expect, test } from "bun:test";
import { NeuralImpulse, MessageStatus } from "../../src/core/message.js";
import { UnifiedValidator } from "../../src/utils/unified_validator.js";

describe("NeuralImpulse - Unit Tests", () => {
    test("getTTL() returns remaining time", () => {
        const now = Date.now();
        const impulse = new NeuralImpulse({ 
            actionIntent: "test",
            expiresAt: now + 5000 
        });
        
        const ttl = impulse.getTTL();
        expect(ttl).toBeGreaterThan(0);
        expect(ttl).toBeLessThanOrEqual(5000);
        
        const impulseNoExpiry = new NeuralImpulse({ actionIntent: "test" });
        expect(impulseNoExpiry.getTTL()).toBeNull();
    });

    test("validate() uses external validator", async () => {
        const validator = new UnifiedValidator();
        const impulse = new NeuralImpulse({ 
            actionIntent: "test",
            content: { field: "value" }
        });
        
        const results = await impulse.validate(validator);
        expect(Array.isArray(results)).toBe(true);
    });

    test("fromDict and toDict parity", () => {
        const original = new NeuralImpulse({
            sessionId: "session-123",
            actionIntent: "intent",
            content: "hello",
            expiresAt: Date.now() + 1000
        });
        original.status = MessageStatus.QUEUED;
        original.addToHistory("AgentA");
        original.addToHistory("AgentB");

        const dict = original.toDict();
        const restored = NeuralImpulse.fromDict(dict);

        expect(restored.sessionId).toBe("session-123");
        expect(restored.content).toBe("hello");
        expect(restored.expiresAt).toBe(dict.expiresAt);
        expect(restored.status).toBe(MessageStatus.QUEUED);
        expect(restored.routingHistory).toEqual(original.routingHistory);
        expect(restored.timestamp).toBe(original.timestamp);
    });
});
