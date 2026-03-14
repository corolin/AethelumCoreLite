import { z } from 'zod';
import { readFileSync, existsSync } from 'fs';
import { resolve, extname } from 'path';

export const MonitoringConfigSchema = z.object({
  enable_prometheus: z.boolean().default(false),
  enable_tracing: z.boolean().default(false),
  enable_metrics_api: z.boolean().default(false),
  prometheus_port: z.number().int().min(1024).max(65535).default(8000),
  prometheus_host: z.string().default('127.0.0.1'),
  jaeger_host: z.string().default('localhost'),
  jaeger_port: z.number().int().min(1024).max(65535).default(6831),
  tracing_sample_rate: z.number().min(0.0).max(1.0).default(0.1),
});

export const SystemConfigSchema = z.object({
  worker_mode: z.enum(['async', 'thread']).default('async'),
  max_workers: z.number().int().positive().default(100),
  queue_size: z.number().int().positive().default(10000),
});

export const APIConfigSchema = z.object({
  metrics_api_host: z.string().default('127.0.0.1'),
  metrics_api_port: z.number().int().min(1024).max(65535).default(8080),
  enable_cors: z.boolean().default(false),
  api_key: z.string().optional().nullable().default(null),
});

export const PerformanceConfigSchema = z.object({
  async_io_concurrency: z.number().int().positive().default(1000),
  hook_timeout: z.number().positive().default(30.0),
});

export const AppConfigSchema = z.object({
  system: SystemConfigSchema.default(() => SystemConfigSchema.parse({})),
  monitoring: MonitoringConfigSchema.default(() => MonitoringConfigSchema.parse({})),
  api: APIConfigSchema.default(() => APIConfigSchema.parse({})),
  performance: PerformanceConfigSchema.default(() => PerformanceConfigSchema.parse({})),
});

export type MonitoringConfig = z.infer<typeof MonitoringConfigSchema>;
export type SystemConfig = z.infer<typeof SystemConfigSchema>;
export type APIConfig = z.infer<typeof APIConfigSchema>;
export type PerformanceConfig = z.infer<typeof PerformanceConfigSchema>;
export type AppConfig = z.infer<typeof AppConfigSchema>;

export class ConfigLoader {
  private static validateConfigPath(configPath: string): string {
    const resolvedPath = resolve(configPath);
    const ext = extname(resolvedPath);
    if (ext && ext !== '.toml') {
      throw new Error(`配置文件必须是 .toml 格式: ${ext}`);
    }
    return resolvedPath;
  }

  public static loadFromFile(configPath: string = 'config.toml'): AppConfig {
    const resolvedPath = this.validateConfigPath(configPath);

    if (!existsSync(resolvedPath)) {
      return this.getDefaultConfig();
    }

    try {
      const fileContent = readFileSync(resolvedPath, 'utf-8');
      
      // We use Bun's built-in TOML parser via the Bun global object
      // (assuming node compatibility makes it visible, or we cast)
      // Since Bun is available globally in the Bun runtime:
      // @ts-ignore
      const parsedData = globalThis.Bun ? Bun.TOML.parse(fileContent) : JSON.parse(fileContent);
      
      // Validate configuration contents
      const result = AppConfigSchema.safeParse(parsedData);
      
      if (!result.success) {
        const errorMsg = '配置验证失败:\n' + result.error.issues.map(err => `  - ${err.path.join('.')}: ${err.message}`).join('\n');
        throw new Error(errorMsg);
      }
      return result.data;
    } catch (e) {
      if (e instanceof Error) {
        throw new Error(`无法加载配置文件: ${e.message}`);
      }
      throw e;
    }
  }

  public static getDefaultConfig(): AppConfig {
    // Parse an empty object because default() covers all fields
    return AppConfigSchema.parse({});
  }

  public static getMonitoringConfig(config: AppConfig): MonitoringConfig {
    return MonitoringConfigSchema.parse(config.monitoring || {});
  }

  public static getSystemConfig(config: AppConfig): SystemConfig {
    return SystemConfigSchema.parse(config.system || {});
  }

  public static getApiConfig(config: AppConfig): APIConfig {
    return APIConfigSchema.parse(config.api || {});
  }

  public static getPerformanceConfig(config: AppConfig): PerformanceConfig {
    return PerformanceConfigSchema.parse(config.performance || {});
  }
}
