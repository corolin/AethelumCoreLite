export enum ValidationSeverity {
    INFO = "info",
    WARNING = "warning",
    ERROR = "error",
    CRITICAL = "critical"
}

export enum ValidationStatus {
    PENDING = "pending",
    RUNNING = "running",
    PASSED = "passed",
    FAILED = "failed",
    SKIPPED = "skipped",
    CANCELLED = "cancelled"
}

export interface ValidationContext {
    data: any;
    fieldPath?: string;
    parentPath?: string;
    metadata?: Record<string, any>;
    sessionId?: string;
}

export class ValidationResult {
    status: ValidationStatus = ValidationStatus.PENDING;
    severity: ValidationSeverity = ValidationSeverity.ERROR;
    message: string = "";
    fieldName: string = "";
    actualValue: any = null;

    public isSuccess(): boolean { return this.status === ValidationStatus.PASSED; }
    public isFailure(): boolean { return this.status === ValidationStatus.FAILED; }
}

export abstract class BaseValidator {
    public name: string;
    public severity: ValidationSeverity;
    public enabled: boolean = true;

    constructor(name: string, severity: ValidationSeverity = ValidationSeverity.ERROR) {
        this.name = name;
        this.severity = severity;
    }

    public async execute(data: any, context: ValidationContext): Promise<ValidationResult> {
        if (!this.enabled) {
            const res = new ValidationResult();
            res.status = ValidationStatus.SKIPPED;
            return res;
        }
        return await this.validate(data, context);
    }

    protected abstract validate(data: any, context: ValidationContext): Promise<ValidationResult>;
}

export class RequiredValidator extends BaseValidator {
    private allowEmpty: boolean;

    constructor(name: string = "required", allowEmpty: boolean = false) {
        super(name);
        this.allowEmpty = allowEmpty;
    }

    protected async validate(data: any, context: ValidationContext): Promise<ValidationResult> {
        const res = new ValidationResult();
        res.fieldName = context.fieldPath || this.name;
        res.actualValue = data;

        if (data === null || data === undefined) {
            res.status = ValidationStatus.FAILED;
            res.message = `字段不可为空`;
            return res;
        }

        if (!this.allowEmpty) {
            if (typeof data === 'string' && data.trim() === '') {
                res.status = ValidationStatus.FAILED;
                res.message = `字段不允许为空字符串`;
                return res;
            }
            if (Array.isArray(data) && data.length === 0) {
                res.status = ValidationStatus.FAILED;
                res.message = `字段不允许为空数组`;
                return res;
            }
            if (typeof data === 'object' && Object.keys(data).length === 0) {
                res.status = ValidationStatus.FAILED;
                res.message = `字段不允许为空对象`;
                return res;
            }
        }

        res.status = ValidationStatus.PASSED;
        return res;
    }
}

export class TypeValidator extends BaseValidator {
    private expectedType: string;

    constructor(expectedType: string, name: string = "type") {
        super(name);
        this.expectedType = expectedType.toLowerCase();
    }

    protected async validate(data: any, context: ValidationContext): Promise<ValidationResult> {
        const res = new ValidationResult();
        res.fieldName = context.fieldPath || this.name;
        res.actualValue = data;

        if (data === null || data === undefined) {
            res.status = ValidationStatus.PASSED; // Type校验不管required
            return res;
        }

        let actualType: string = typeof data;
        if (Array.isArray(data)) actualType = 'array';

        if (actualType !== this.expectedType) {
            res.status = ValidationStatus.FAILED;
            res.message = `类型不匹配. 期望: ${this.expectedType}, 实际: ${actualType}`;
            return res;
        }

        res.status = ValidationStatus.PASSED;
        return res;
    }
}

export class UnifiedValidator {
    private validators: Map<string, BaseValidator[]> = new Map();

    public addRule(fieldPath: string, validator: BaseValidator): void {
        if (!this.validators.has(fieldPath)) {
            this.validators.set(fieldPath, []);
        }
        this.validators.get(fieldPath)!.push(validator);
    }

    public async validate(data: Record<string, any>, globalContext?: Partial<ValidationContext>): Promise<ValidationResult[]> {
        const results: ValidationResult[] = [];

        for (const [fieldPath, fieldValidators] of this.validators.entries()) {
            // 支持简单的点分割路径提取
            const val = this.extractValue(data, fieldPath);

            const context: ValidationContext = {
                data: data,
                fieldPath: fieldPath,
                ...globalContext
            };

            for (const validator of fieldValidators) {
                const res = await validator.execute(val, context);
                results.push(res);

                // 遇到首个失败且是 ERROR/CRITICAL，停止当前字段的后续校验
                if (res.isFailure() && (res.severity === ValidationSeverity.ERROR || res.severity === ValidationSeverity.CRITICAL)) {
                    break;
                }
            }
        }

        return results;
    }

    private extractValue(obj: any, path: string): any {
        return path.split('.').reduce((acc, part) => acc && acc[part], obj);
    }
}
