import { describe, expect, test } from "bun:test";
import { MetricsAPI, MetricsAPIServer } from "../../src/api/metrics_api.js";

describe("MetricsAPI (zero-dependency native fetch)", () => {
    test("health endpoint works without auth when apiKey omitted", async () => {
        const api = new MetricsAPI(null);
        const res = await api.app.fetch(new Request("http://localhost/api/v1/health"));
        expect(res.status).toBe(200);
        const body = await res.json() as Record<string, unknown>;
        expect(body.status).toBe("healthy");
        expect(body.service).toBe("aethelum-core-lite");
        expect(body.authenticated).toBe(false);
    });

    test("metrics returns 503 when router not initialized", async () => {
        const api = new MetricsAPI(null);
        const res = await api.app.fetch(new Request("http://localhost/api/v1/metrics"));
        expect(res.status).toBe(503);
        const body = await res.json() as Record<string, unknown>;
        expect(body.detail).toBe("Router not initialized");
    });

    test("auth middleware enforces Bearer token and supports setApiKey rotation", async () => {
        const api = new MetricsAPI(null, "secret-1");

        const unauth = await api.app.fetch(new Request("http://localhost/api/v1/health"));
        expect(unauth.status).toBe(401);

        const wrong = await api.app.fetch(new Request("http://localhost/api/v1/health", {
            headers: { Authorization: "Bearer wrong-key" },
        }));
        expect(wrong.status).toBe(401);

        const ok = await api.app.fetch(new Request("http://localhost/api/v1/health", {
            headers: { Authorization: "Bearer secret-1" },
        }));
        expect(ok.status).toBe(200);

        api.setApiKey("secret-2");
        const oldKey = await api.app.fetch(new Request("http://localhost/api/v1/health", {
            headers: { Authorization: "Bearer secret-1" },
        }));
        expect(oldKey.status).toBe(401);

        const newKey = await api.app.fetch(new Request("http://localhost/api/v1/health", {
            headers: { Authorization: "Bearer secret-2" },
        }));
        expect(newKey.status).toBe(200);
    });

    test("returns metrics from router and 404 on unknown route", async () => {
        const mockRouter = {
            getQueueMetrics: () => ({ q1: { depth: 2 } }),
        } as unknown as Parameters<typeof MetricsAPI.prototype.setRouter>[0];

        const api = new MetricsAPI(mockRouter, "k1");
        const res = await api.app.fetch(new Request("http://localhost/api/v1/metrics", {
            headers: { Authorization: "Bearer k1" },
        }));
        expect(res.status).toBe(200);
        expect(await res.json()).toEqual({ q1: { depth: 2 } });

        const notFound = await api.app.fetch(new Request("http://localhost/api/v1/unknown", {
            headers: { Authorization: "Bearer k1" },
        }));
        expect(notFound.status).toBe(404);
    });

    test("MetricsAPIServer requires apiKey", () => {
        expect(() => new MetricsAPIServer("127.0.0.1", 0, null)).toThrow();
    });
});
