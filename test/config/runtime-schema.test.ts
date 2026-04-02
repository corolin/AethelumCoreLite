import { describe, expect, test } from "bun:test";
import {
  CoreLiteRuntimeSchema,
  parseCoreLiteRuntimeConfig,
} from "../../src/config/runtime-schema.js";

describe("CoreLite runtime schema", () => {
  test("applies defaults for minimal runtime config", () => {
    const parsed = parseCoreLiteRuntimeConfig({});

    expect(parsed.router.enableWal).toBe(true);
    expect(parsed.router.dynamicQueues.mode).toBe("allow");
    expect(parsed.profiles).toEqual([]);
    expect(parsed.queues).toEqual([]);
    expect(parsed.workers).toEqual([]);
  });

  test("validates queue, worker, and profile definitions", () => {
    const parsed = CoreLiteRuntimeSchema.parse({
      profiles: [
        {
          id: "durable-default",
          plugins: [
            {
              plugin: "wal",
              options: { walDir: "runtime_wal" },
            },
          ],
        },
      ],
      queues: [
        {
          id: "Q_PROCESS",
          capacity: 1000,
          hooks: {
            profiles: ["durable-default"],
          },
          tags: ["core"],
        },
      ],
      workers: [
        {
          id: "ProcessWorker",
          kind: "llm",
          inputQueueId: "Q_PROCESS",
          hooks: {
            plugins: [
              {
                plugin: "audit-post",
                enabled: true,
                priorityOffset: 10,
              },
            ],
          },
          config: {
            model: "mini",
          },
        },
      ],
      router: {
        enableWal: false,
        dynamicQueues: {
          mode: "match_profile",
          hooks: {
            profiles: ["durable-default"],
          },
          allowPatterns: ["^Q_TMP_", "^Q_PLUGIN_"],
        },
      },
    });

    expect(parsed.profiles[0]?.plugins[0]?.plugin).toBe("wal");
    expect(parsed.queues[0]?.hooks.profiles).toEqual(["durable-default"]);
    expect(parsed.workers[0]?.inputQueueId).toBe("Q_PROCESS");
    expect(parsed.router.dynamicQueues.mode).toBe("match_profile");
  });

  test("rejects invalid worker definitions", () => {
    expect(() =>
      CoreLiteRuntimeSchema.parse({
        workers: [
          {
            id: "",
            kind: "llm",
            inputQueueId: "Q_PROCESS",
          },
        ],
      }),
    ).toThrow();
  });
});
