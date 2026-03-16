import { describe, expect, test } from "bun:test";
import { ConfigLoader } from "../../src/config/config_loader.js";
import fs from 'fs';
import path from 'path';
import os from 'os';

describe("ConfigLoader - Unit Tests", () => {
    test("getDefaultConfig() returns sensible defaults", () => {
        const config = ConfigLoader.getDefaultConfig();
        expect(config.system.worker_mode).toBe('async');
        expect(config.system.max_workers).toBe(100);
        expect(config.api.metrics_api_port).toBe(8080);
    });

    test("loadFromFile() with missing file returns defaults", () => {
        const config = ConfigLoader.loadFromFile("non_existent_file.toml");
        expect(config.system.worker_mode).toBe('async');
    });

    test("loadFromFile() with valid TOML", () => {
        const tempToml = path.join(os.tmpdir(), `test_config_${Date.now()}.toml`);
        const content = `
[system]
worker_mode = "thread"
max_workers = 50

[api]
metrics_api_port = 9000
`;
        fs.writeFileSync(tempToml, content);
        
        try {
            const config = ConfigLoader.loadFromFile(tempToml);
            expect(config.system.worker_mode).toBe('thread');
            expect(config.system.max_workers).toBe(50);
            expect(config.api.metrics_api_port).toBe(9000);
        } finally {
            if (fs.existsSync(tempToml)) fs.unlinkSync(tempToml);
        }
    });

    test("loadFromFile() with invalid TOML throws error", () => {
        const tempToml = path.join(os.tmpdir(), `test_inv_${Date.now()}.toml`);
        fs.writeFileSync(tempToml, "[invalid_toml\nmissing_closing_bracket = 1");
        
        try {
            expect(() => ConfigLoader.loadFromFile(tempToml)).toThrow();
        } finally {
            if (fs.existsSync(tempToml)) fs.unlinkSync(tempToml);
        }
    });

    test("loadFromFile() with invalid extension throws error", () => {
        expect(() => ConfigLoader.loadFromFile("config.json")).toThrow(/必须是 .toml 格式/);
    });

    test("loadFromFile() with Zod validation failure throws error", () => {
        const tempToml = path.join(os.tmpdir(), `test_val_${Date.now()}.toml`);
        // missing required field or invalid type
        fs.writeFileSync(tempToml, `
[system]
worker_mode = 123
`);
        
        try {
            expect(() => ConfigLoader.loadFromFile(tempToml)).toThrow(/配置验证失败/);
        } finally {
            if (fs.existsSync(tempToml)) fs.unlinkSync(tempToml);
        }
    });

    test("Helper methods getSystemConfig etc", () => {
        const config = ConfigLoader.getDefaultConfig();
        expect(ConfigLoader.getSystemConfig(config)).toBeDefined();
        expect(ConfigLoader.getApiConfig(config)).toBeDefined();
        expect(ConfigLoader.getMonitoringConfig(config)).toBeDefined();
        expect(ConfigLoader.getPerformanceConfig(config)).toBeDefined();
    });
});
