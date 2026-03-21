import { describe, expect, test, beforeEach } from "bun:test";
import { 
    UnifiedValidator, 
    RequiredValidator, 
    TypeValidator, 
    ValidationStatus, 
    ValidationSeverity, 
    BaseValidator,
    ValidationResult
} from "../../src/utils/unified_validator.js";

describe("UnifiedValidator - Unit Tests", () => {
    let validator: UnifiedValidator;

    beforeEach(() => {
        validator = new UnifiedValidator();
    });

    test("RequiredValidator basic logic", async () => {
        const req = new RequiredValidator("test_field", false);
        
        // Pass
        let res = await req.execute("hello", { fieldPath: "f" } as any);
        expect(res.status).toBe(ValidationStatus.PASSED);

        // Fail null
        res = await req.execute(null, { fieldPath: "f" } as any);
        expect(res.status).toBe(ValidationStatus.FAILED);
        expect(res.message).toContain("不可为空");

        // Fail empty string
        res = await req.execute("", { fieldPath: "f" } as any);
        expect(res.status).toBe(ValidationStatus.FAILED);
        expect(res.message).toContain("不允许为空字符串");

        // Fail empty array
        res = await req.execute([], { fieldPath: "f" } as any);
        expect(res.status).toBe(ValidationStatus.FAILED);

        // Fail empty object
        res = await req.execute({}, { fieldPath: "f" } as any);
        expect(res.status).toBe(ValidationStatus.FAILED);
    });

    test("RequiredValidator allowEmpty", async () => {
        const req = new RequiredValidator("test_field", true);
        const res = await req.execute("", { fieldPath: "f" } as any);
        expect(res.status).toBe(ValidationStatus.PASSED);
    });

    test("TypeValidator basic logic", async () => {
        const typeV = new TypeValidator("string");
        
        expect((await typeV.execute("hi", {} as any)).status).toBe(ValidationStatus.PASSED);
        expect((await typeV.execute(123, {} as any)).status).toBe(ValidationStatus.FAILED);
        
        const arrayV = new TypeValidator("array");
        expect((await arrayV.execute([], {} as any)).status).toBe(ValidationStatus.PASSED);
        expect((await arrayV.execute({}, {} as any)).status).toBe(ValidationStatus.FAILED);

        // TypeValidator should skip null/undefined (let RequiredValidator handle it)
        expect((await typeV.execute(null, {} as any)).status).toBe(ValidationStatus.PASSED);
    });

    test("UnifiedValidator complex nested validation", async () => {
        validator.addRule("user.name", new RequiredValidator());
        validator.addRule("user.age", new TypeValidator("number"));
        
        const data = {
            user: {
                name: "Alice",
                age: 25
            }
        };

        const results = await validator.validate(data);
        expect(results.every(r => r.isSuccess())).toBe(true);
        expect(results.length).toBe(2);

        const badData = {
            user: {
                name: "",
                age: "too old"
            }
        };
        const badResults = await validator.validate(badData);
        expect(badResults.filter(r => r.isFailure()).length).toBe(2);
    });

    test("Validator skipping when disabled", async () => {
        const req = new RequiredValidator();
        req.enabled = false;
        validator.addRule("field", req);
        
        const results = await validator.validate({ field: null });
        expect(results[0]!.status).toBe(ValidationStatus.SKIPPED);
    });

    test("Halt on first error in same field", async () => {
        // Add two validators to same field
        validator.addRule("f", new RequiredValidator());
        validator.addRule("f", new TypeValidator("number"));

        // If first fails with ERROR severity, second should not run
        const results = await validator.validate({ f: "" });
        expect(results.length).toBe(1); // Only RequiredValidator ran
        expect(results[0]!.status).toBe(ValidationStatus.FAILED);
    });

    test("ValidationResult isSuccess/isFailure", () => {
        const res = new ValidationResult();
        res.status = ValidationStatus.PASSED;
        expect(res.isSuccess()).toBe(true);
        expect(res.isFailure()).toBe(false);
        
        res.status = ValidationStatus.FAILED;
        expect(res.isSuccess()).toBe(false);
        expect(res.isFailure()).toBe(true);
    });
});
