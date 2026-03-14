import { createHash } from 'crypto';
import type { BaseValidator, ValidationContext, ValidationResult } from './unified_validator.js';

export class ValidationCacheKey {
    constructor(
        public validator_name: string,
        public data_hash: string,
        public context_hash: string
    ) { }

    static create(validator_name: string, data: any, context: any): ValidationCacheKey {
        return new ValidationCacheKey(
            validator_name,
            ValidationCacheKey.hashData(data),
            ValidationCacheKey.hashData(context)
        );
    }

    static hashData(data: any): string {
        const str = typeof data === 'object' ? JSON.stringify(data) : String(data);
        return createHash('sha256').update(str).digest('hex').substring(0, 16);
    }

    toString(): string {
        return `${this.validator_name}:${this.data_hash}:${this.context_hash}`;
    }
}

export class ValidationCache {
    private cache = new Map<string, { result: any; created_at: number; access_count: number }>();
    private hits = 0;
    private misses = 0;

    constructor(public maxSize: number = 1000, public ttl: number = 300) { }

    get(validator_name: string, data: any, context: any): any | null {
        const key = ValidationCacheKey.create(validator_name, data, context).toString();
        const entry = this.cache.get(key);

        if (!entry) {
            this.misses++;
            return null;
        }

        if (Date.now() / 1000 - entry.created_at > this.ttl) {
            this.cache.delete(key);
            this.misses++;
            return null;
        }

        entry.access_count++;
        this.hits++;

        // LRU move to end
        this.cache.delete(key);
        this.cache.set(key, entry);

        return entry.result;
    }

    put(validator_name: string, data: any, context: any, result: any): void {
        if (this.cache.size >= this.maxSize) {
            const firstKey = this.cache.keys().next().value;
            if (firstKey) this.cache.delete(firstKey);
        }
        const key = ValidationCacheKey.create(validator_name, data, context).toString();
        this.cache.set(key, { result, created_at: Date.now() / 1000, access_count: 0 });
    }

    getStats() {
        return {
            size: this.cache.size,
            hits: this.hits,
            misses: this.misses,
            hitRate: this.hits / Math.max(1, this.hits + this.misses) * 100
        };
    }
}

class ValidationPerformanceOptimizer {
    public cache = new ValidationCache();

    async validateAsyncWithOptimization(validators: BaseValidator[], data: any, context: ValidationContext): Promise<ValidationResult[]> {
        const results: ValidationResult[] = [];

        for (const v of validators) {
            let res = this.cache.get(v.name, data, context);
            if (!res) {
                res = await v.execute(data, context);
                this.cache.put(v.name, data, context, res);
            }
            results.push(res);
        }

        return results;
    }
}

export const optimizer = new ValidationPerformanceOptimizer();
export const validateAsyncWithOptimization = (validators: BaseValidator[], data: any, context: ValidationContext) =>
    optimizer.validateAsyncWithOptimization(validators, data, context);
