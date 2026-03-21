import { describe, expect, test, beforeEach, afterEach, spyOn } from "bun:test";
import { AsyncErrorHandler } from "../../src/core/error_handler.js";
import { CoreLiteRouter } from "../../src/core/router.js";
import { NeuralImpulse, MessageStatus } from "../../src/core/message.js";

describe("AsyncErrorHandler - Unit Tests", () => {
    let errorHandler: AsyncErrorHandler;
    let router: CoreLiteRouter;

    beforeEach(() => {
        router = new CoreLiteRouter(false);
        errorHandler = new AsyncErrorHandler(router);
    });

    afterEach(async () => {
        await router.stop();
    });

    test("handleError() diverts message to Q_ERROR and adds metadata", async () => {
        const impulse = new NeuralImpulse({ actionIntent: "original_task" });
        const error = new Error("Something went wrong");
        const context = { workerId: "TestWorker", stage: "testing" };

        (router as any).isActive = true;
        
        // Use the router's own errorHandler to ensure perfect integration
        await router.errorHandler.handleError(error, impulse, context);

        expect(impulse.status).toBe(MessageStatus.FAILED);
        // The error impulse is what's routed, not the original impulse necessarily for all fields
        // but handleError creates a new impulse. We need to check Q_ERROR content.
        
        const qError = (router as any).queues.get("Q_ERROR");
        const retrieved = await qError.asyncGet(100);
        expect(retrieved).not.toBeNull();
        expect(retrieved?.metadata["error_context"]?.stage).toBe("testing");
        expect(retrieved?.metadata["error_message"]).toContain("Something went wrong");
    });

    test("handleError() handles missing impulse gracefully", async () => {
        const error = new Error("Fatal system error");
        const spy = spyOn(console, "error").mockImplementation(() => {});
        const infoSpy = spyOn(console, "info").mockImplementation(() => {});
        
        await errorHandler.handleError(error, null as any, { stage: "bootstrap" });
        
        expect(spy).toHaveBeenCalled();
        
        const stats = errorHandler.getErrorStats();
        expect(stats["process_error"]).toBeGreaterThan(0);
        
        errorHandler.resetStats();
        expect(errorHandler.getErrorStats()["process_error"]).toBe(0);
        
        spy.mockRestore();
        infoSpy.mockRestore();
    });
});
