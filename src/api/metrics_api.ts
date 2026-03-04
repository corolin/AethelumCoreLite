import { Hono } from 'hono';
import { bearerAuth } from 'hono/bearer-auth';
import type { AsyncSomaRouter } from '../core/router';

export class MetricsAPI {
    public app: Hono;
    private _router: AsyncSomaRouter | null;
    private _apiKey: string;
    private _requireAuth: boolean;

    constructor(router: AsyncSomaRouter | null = null, apiKey?: string) {
        if (!apiKey) {
            throw new Error("必须设置apiKey（安全要求：禁止无认证访问）");
        }

        this._router = router;
        this._apiKey = apiKey;
        this._requireAuth = true;

        this.app = new Hono();
        this.setupRoutes();
    }

    private setupRoutes() {
        // Middleware for Auth
        this.app.use('/api/v1/*', async (c, next) => {
            const auth = bearerAuth({ token: this._apiKey });
            return auth(c, next);
        });

        this.app.get('/api/v1/health', (c) => {
            return c.json({
                status: 'healthy',
                timestamp: Date.now() / 1000,
                service: 'aethelum-core-lite',
                authenticated: this._requireAuth
            });
        });

        this.app.get('/api/v1/metrics', async (c) => {
            if (!this._router) {
                return c.json({ detail: "Router not initialized" }, 503);
            }
            // Assuming getMetrics() exists or we map to router.getStats()
            const metrics = typeof (this._router as any).getMetrics === 'function'
                ? await (this._router as any).getMetrics()
                : await (this._router as any).getStats?.() || {};

            return c.json(metrics);
        });
    }

    public setRouter(router: AsyncSomaRouter) {
        this._router = router;
    }

    public setApiKey(apiKey: string) {
        this._apiKey = apiKey;
        this._requireAuth = !!apiKey;
    }
}

export class MetricsAPIServer {
    private metricsApi: MetricsAPI;
    private server: any;

    constructor(
        public host: string = "127.0.0.1",
        public port: number = 8080,
        router: AsyncSomaRouter | null = null,
        apiKey?: string
    ) {
        if (!apiKey) {
            throw new Error("必须设置apiKey（安全要求：禁止无认证访问）");
        }
        this.metricsApi = new MetricsAPI(router, apiKey);
    }

    public start() {
        this.server = Bun.serve({
            fetch: this.metricsApi.app.fetch,
            port: this.port,
            hostname: this.host
        });
        console.log(`Metrics API Server strted on http://${this.host}:${this.port}`);
    }

    public getApp() {
        return this.metricsApi.app;
    }

    public stop() {
        if (this.server) {
            this.server.stop();
        }
    }
}
