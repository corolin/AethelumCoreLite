import { z } from "zod";

const StringMapSchema = z.record(z.string(), z.unknown());

export const HookPluginSpecSchema = z.object({
  plugin: z.string().min(1),
  enabled: z.boolean().default(true),
  priorityOffset: z.number().int().default(0),
  options: StringMapSchema.default({}),
});

export const HookAssemblySchema = z.object({
  profiles: z.array(z.string().min(1)).default([]),
  plugins: z.array(HookPluginSpecSchema).default([]),
});

export const QueueRuntimeDefinitionSchema = z.object({
  id: z.string().min(1),
  capacity: z.number().int().min(0).default(0),
  autoExpand: z.boolean().default(true),
  shrinkIntervalMs: z.number().int().positive().default(10 * 60 * 1000),
  hooks: HookAssemblySchema.default(() => HookAssemblySchema.parse({})),
  tags: z.array(z.string().min(1)).default([]),
  metadata: StringMapSchema.default({}),
});

export const WorkerRuntimeDefinitionSchema = z.object({
  id: z.string().min(1),
  kind: z.string().min(1),
  inputQueueId: z.string().min(1),
  hooks: HookAssemblySchema.default(() => HookAssemblySchema.parse({})),
  tags: z.array(z.string().min(1)).default([]),
  metadata: StringMapSchema.default({}),
  config: StringMapSchema.default({}),
});

export const HookProfileDefinitionSchema = z.object({
  id: z.string().min(1),
  plugins: z.array(HookPluginSpecSchema).min(1),
  description: z.string().optional(),
});

export const DynamicQueueStrategySchema = z.object({
  mode: z.enum(["allow", "deny", "match_profile"]).default("allow"),
  defaultCapacity: z.number().int().min(0).default(1000),
  defaultAutoExpand: z.boolean().default(true),
  defaultShrinkIntervalMs: z.number().int().positive().default(10 * 60 * 1000),
  hooks: HookAssemblySchema.default(() => HookAssemblySchema.parse({})),
  tags: z.array(z.string().min(1)).default([]),
  allowPatterns: z.array(z.string().min(1)).default([]),
});

export const RouterRuntimeDefinitionSchema = z.object({
  enableWal: z.boolean().default(true),
  skipBuiltInQueues: z.boolean().default(false),
  builtInQueues: z.array(QueueRuntimeDefinitionSchema).default([]),
  dynamicQueues: DynamicQueueStrategySchema.default(() => DynamicQueueStrategySchema.parse({})),
});

export const CoreLiteRuntimeSchema = z.object({
  router: RouterRuntimeDefinitionSchema.default(() => RouterRuntimeDefinitionSchema.parse({})),
  profiles: z.array(HookProfileDefinitionSchema).default([]),
  queues: z.array(QueueRuntimeDefinitionSchema).default([]),
  workers: z.array(WorkerRuntimeDefinitionSchema).default([]),
});

export type HookPluginSpecConfig = z.infer<typeof HookPluginSpecSchema>;
export type HookAssemblyConfig = z.infer<typeof HookAssemblySchema>;
export type QueueRuntimeDefinition = z.infer<typeof QueueRuntimeDefinitionSchema>;
export type WorkerRuntimeDefinition = z.infer<typeof WorkerRuntimeDefinitionSchema>;
export type HookProfileDefinition = z.infer<typeof HookProfileDefinitionSchema>;
export type DynamicQueueStrategy = z.infer<typeof DynamicQueueStrategySchema>;
export type RouterRuntimeDefinition = z.infer<typeof RouterRuntimeDefinitionSchema>;
export type CoreLiteRuntimeConfig = z.infer<typeof CoreLiteRuntimeSchema>;

export function parseCoreLiteRuntimeConfig(input: unknown): CoreLiteRuntimeConfig {
  return CoreLiteRuntimeSchema.parse(input);
}
