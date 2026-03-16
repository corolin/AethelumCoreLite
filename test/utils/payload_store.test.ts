import { describe, expect, test, beforeEach, afterEach } from "bun:test";
import { LocalPayloadStore } from "../../src/utils/payload_store.js";
import fs from 'fs';
import path from 'path';
import os from 'os';

describe("LocalPayloadStore - Unit Tests", () => {
    let store: LocalPayloadStore;
    let tempDir: string;

    beforeEach(() => {
        tempDir = path.join(os.tmpdir(), `aethelum_test_${Date.now()}`);
        store = new LocalPayloadStore(tempDir);
    });

    afterEach(() => {
        if (fs.existsSync(tempDir)) {
            fs.rmSync(tempDir, { recursive: true, force: true });
        }
    });

    test("savePayload() and loadPayload() basic flow", async () => {
        const content = "Hello World Payload";
        const sessionId = "session-123";
        const conversationId = "conv-456";

        const ref = await store.savePayload(content, sessionId, conversationId);
        
        expect(ref.type).toBe("reference");
        expect(ref.uri).toContain(`NeuralImpulsePayload://${sessionId}/${conversationId}/`);
        expect(ref.uri).toContain(".md");

        const loaded = await store.loadPayload(ref.uri);
        expect(loaded).toBe(content);
    });

    test("loadPayload() with invalid uri", async () => {
        expect(await store.loadPayload("invalid://something")).toBeNull();
        expect(await store.loadPayload("NeuralImpulsePayload://too/few")).toBeNull();
        expect(await store.loadPayload("NeuralImpulsePayload://session/conv/dotdot/..")).toBeNull();
    });

    test("isPayloadReference() check", () => {
        expect(store.isPayloadReference({ type: "reference", uri: "NeuralImpulsePayload://a/b/c.md" })).toBe(true);
        expect(store.isPayloadReference({ type: "not_ref" })).toBe(false);
        expect(store.isPayloadReference(null)).toBe(false);
        expect(store.isPayloadReference("just a string")).toBe(false);
    });

    test("Path traversal prevention on save", async () => {
        await expect(store.savePayload("content", "../hacker")).rejects.toThrow("sessionId 包含非法字符");
    });

    test("loadPayload missing file returns null", async () => {
        const uri = "NeuralImpulsePayload://session/conv/nonexistent.md";
        expect(await store.loadPayload(uri)).toBeNull();
    });
});
