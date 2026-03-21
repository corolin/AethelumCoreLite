import { Hono } from 'hono';
import type { CoreLiteRouter } from '../core/router.js';

export class MetricsAPI {
    public app: Hono;
    private _router: CoreLiteRouter | null;
    private _apiKey: string;
    private _requireAuth: boolean;

    constructor(router: CoreLiteRouter | null = null, apiKey?: string) {
        this._router = router;
        this._apiKey = apiKey || '';
        this._requireAuth = !!apiKey; // 有 apiKey 才需要认证

        this.app = new Hono();
        this.setupRoutes();
    }

    private setupRoutes() {
        // Middleware for Auth — 直接读取 this._apiKey，确保 setApiKey() 轮换后立即生效
        this.app.use('/api/v1/*', async (c, next) => {
            if (!this._requireAuth) {
                return await next(); // 无认证模式，直接放行
            }
            const authHeader = c.req.header('Authorization');
            if (!authHeader || !authHeader.startsWith('Bearer ') || authHeader.slice(7) !== this._apiKey) {
                return c.json({ error: 'Unauthorized' }, 401);
            }
            await next();
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
            const metrics = this._router.getQueueMetrics();

            return c.json(metrics);
        });
    }

    public setRouter(router: CoreLiteRouter) {
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
        router: CoreLiteRouter | null = null,
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
        console.log(`Metrics API Server started on http://${this.host}:${this.port}`);
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
