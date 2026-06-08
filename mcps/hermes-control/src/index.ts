#!/usr/bin/env node
/**
 * hermes-control MCP — expoe backend Hermes Cloud Studio como tools MCP.
 * Stdio transport. Le HERMES_API_URL + HERMES_AUTH_TOKEN do env.
 */
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";

const API_URL = process.env.HERMES_API_URL ?? "http://localhost:8500";
const AUTH_TOKEN = process.env.HERMES_AUTH_TOKEN ?? "";

if (!AUTH_TOKEN) {
  console.error("[hermes-control] WARN: HERMES_AUTH_TOKEN not set — calls will likely 401");
}

async function hermesFetch(
  path: string,
  options: { method?: string; body?: unknown; query?: Record<string, string | number | boolean | undefined> } = {}
): Promise<unknown> {
  const { method = "GET", body, query } = options;
  const url = new URL(path, API_URL);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }
  }
  const headers: Record<string, string> = {
    "X-Hermes-Token": AUTH_TOKEN,
    "Content-Type": "application/json",
  };
  const res = await fetch(url.toString(), {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`Hermes API ${res.status} ${res.statusText} on ${path}: ${text.slice(0, 500)}`);
  }
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

const TOOLS = [
  {
    name: "hermes_status",
    description:
      "Snapshot completo de saúde: PC backend, VM backend, LinkedIn health, daemon state, ultimos erros. Use no inicio de qualquer sessao Hermes ou quando algo parecer travado.",
    inputSchema: z.object({}).strict(),
    handler: async () => {
      const [status, daemon, liHealth] = await Promise.allSettled([
        hermesFetch("/api/hermes/status"),
        hermesFetch("/api/daemon/state"),
        hermesFetch("/api/linkedin/health"),
      ]);
      return {
        pc_vm_status: status.status === "fulfilled" ? status.value : { error: String(status.reason) },
        daemon: daemon.status === "fulfilled" ? daemon.value : { error: String(daemon.reason) },
        linkedin_health: liHealth.status === "fulfilled" ? liHealth.value : { error: String(liHealth.reason) },
      };
    },
  },
  {
    name: "list_prospects",
    description:
      "Lista prospects com filtros. Use pra investigar pipeline, achar oportunidades por cidade/categoria/score.",
    inputSchema: z
      .object({
        city: z.string().optional().describe("Filtro cidade (ex: Cuiaba)"),
        category: z.string().optional().describe("Categoria negocio"),
        stage: z.enum(["discovered", "qualified", "audited", "outreach", "engaged"]).optional(),
        has_website: z.boolean().optional(),
        min_score: z.number().optional(),
        limit: z.number().min(1).max(500).default(50),
      })
      .strict(),
    handler: async (args: Record<string, unknown>) =>
      hermesFetch("/api/prospects", { query: args as Record<string, string | number | boolean | undefined> }),
  },
  {
    name: "daemon_state",
    description: "Estado atual do Hermes Daemon orchestrator (P1-P7, fila, circuit breakers, working hours).",
    inputSchema: z.object({}).strict(),
    handler: async () => hermesFetch("/api/daemon/state"),
  },
  {
    name: "daemon_control",
    description: "Pause ou retoma o daemon Hermes. Use 'pause' antes de manutencao, 'resume' depois.",
    inputSchema: z.object({ action: z.enum(["pause", "resume"]) }).strict(),
    handler: async (args: Record<string, unknown>) => {
      const action = args.action as "pause" | "resume";
      return hermesFetch(`/api/daemon/${action}`, { method: "POST" });
    },
  },
  {
    name: "li_health",
    description:
      "Health do LinkedIn: session OK, rate-limits, warm-up day, working hours, ultimo probe. force_refresh=true forca probe novo via SOCKS5.",
    inputSchema: z.object({ force_refresh: z.boolean().default(false) }).strict(),
    handler: async (args: Record<string, unknown>) =>
      hermesFetch("/api/linkedin/health", { query: { force_refresh: args.force_refresh ? 1 : undefined } }),
  },
  {
    name: "li_rate_limits",
    description: "Snapshot dos limites diarios/semanais LinkedIn (views, connects, comments) e quanto ja foi usado hoje.",
    inputSchema: z.object({}).strict(),
    handler: async () => hermesFetch("/api/linkedin/rate-limits"),
  },
  {
    name: "li_campaigns",
    description: "Lista campanhas LinkedIn (running, scheduled, completed) com status e progresso.",
    inputSchema: z
      .object({
        status: z.enum(["running", "scheduled", "completed", "cancelled", "all"]).default("all"),
      })
      .strict(),
    handler: async (args: Record<string, unknown>) =>
      hermesFetch("/api/linkedin/campaigns", { query: { status: args.status as string } }),
  },
  {
    name: "activities",
    description: "Activity log paginado (eventos do daemon + campanhas + scraper).",
    inputSchema: z
      .object({
        limit: z.number().min(1).max(200).default(30),
        offset: z.number().default(0),
      })
      .strict(),
    handler: async (args: Record<string, unknown>) =>
      hermesFetch("/api/activities", { query: args as Record<string, string | number | boolean | undefined> }),
  },
  {
    name: "pipeline_list",
    description: "Lista templates de pipeline + executions recentes.",
    inputSchema: z.object({}).strict(),
    handler: async () => hermesFetch("/api/pipelines"),
  },
  {
    name: "pipeline_execute",
    description: "Executa um pipeline template pelo ID. Retorna execution_id pra acompanhar.",
    inputSchema: z.object({ pipeline_id: z.number() }).strict(),
    handler: async (args: Record<string, unknown>) =>
      hermesFetch(`/api/pipelines/${args.pipeline_id}/execute`, { method: "POST" }),
  },
  {
    name: "scraper_status",
    description: "Estado do scraper Google Maps (gosom/night). Retorna PID, progresso, ultimo log.",
    inputSchema: z.object({}).strict(),
    handler: async () => hermesFetch("/api/scraper/status"),
  },
  {
    name: "scraper_start",
    description: "Inicia scraper. cities/categories opcionais — sem args usa default. only_no_site=true so coleta sem website.",
    inputSchema: z
      .object({
        cities: z.array(z.string()).optional(),
        categories: z.array(z.string()).optional(),
        only_no_site: z.boolean().default(false),
      })
      .strict(),
    handler: async (args: Record<string, unknown>) =>
      hermesFetch("/api/scraper/start", { method: "POST", body: args }),
  },
  {
    name: "audit_start",
    description: "Inicia batch audit de prospects (web audit scoring 0-100). batch_size opcional.",
    inputSchema: z
      .object({
        batch_size: z.number().min(1).max(500).default(50),
        only_pending: z.boolean().default(true),
      })
      .strict(),
    handler: async (args: Record<string, unknown>) =>
      hermesFetch("/api/audit/start", { method: "POST", body: args }),
  },
  {
    name: "skills_list",
    description: "Lista skills YAML do Hermes Agent VM (name, description, model, active).",
    inputSchema: z.object({}).strict(),
    handler: async () => hermesFetch("/api/hermes/skills"),
  },
  {
    name: "skill_toggle",
    description: "Ativa/desativa uma skill pelo nome.",
    inputSchema: z.object({ name: z.string(), active: z.boolean() }).strict(),
    handler: async (args: Record<string, unknown>) =>
      hermesFetch(`/api/hermes/skills/${args.name}`, { method: "PATCH", body: { active: args.active } }),
  },
  {
    name: "server_restart",
    description: "Restart serviços. target: 'local' (server.py PC), 'vm' (hermes_api_v2 na VM), 'all'.",
    inputSchema: z.object({ target: z.enum(["local", "vm", "all"]) }).strict(),
    handler: async (args: Record<string, unknown>) =>
      hermesFetch(`/api/server/restart-${args.target}`, { method: "POST" }),
  },
];

const server = new Server(
  { name: "hermes-control", version: "0.1.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: TOOLS.map((t) => ({
    name: t.name,
    description: t.description,
    inputSchema: zodToJsonSchema(t.inputSchema),
  })),
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const tool = TOOLS.find((t) => t.name === request.params.name);
  if (!tool) {
    return { content: [{ type: "text", text: `Unknown tool: ${request.params.name}` }], isError: true };
  }
  try {
    const args = tool.inputSchema.parse(request.params.arguments ?? {});
    const result = await tool.handler(args as Record<string, unknown>);
    return {
      content: [{ type: "text", text: typeof result === "string" ? result : JSON.stringify(result, null, 2) }],
    };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return { content: [{ type: "text", text: `Error: ${msg}` }], isError: true };
  }
});

/** Minimal zod -> JSON Schema (objects with primitive/enum/array/optional props). */
function zodToJsonSchema(schema: z.ZodTypeAny): Record<string, unknown> {
  if (schema instanceof z.ZodObject) {
    const shape = schema.shape as Record<string, z.ZodTypeAny>;
    const properties: Record<string, unknown> = {};
    const required: string[] = [];
    for (const [key, value] of Object.entries(shape)) {
      properties[key] = zodFieldToJsonSchema(value);
      if (!value.isOptional()) required.push(key);
    }
    return {
      type: "object",
      properties,
      ...(required.length ? { required } : {}),
      additionalProperties: false,
    };
  }
  return { type: "object" };
}

function zodFieldToJsonSchema(field: z.ZodTypeAny): Record<string, unknown> {
  const description = field.description;
  const wrap = (obj: Record<string, unknown>) => (description ? { ...obj, description } : obj);
  let inner: z.ZodTypeAny = field;
  if (inner instanceof z.ZodDefault) inner = inner._def.innerType;
  if (inner instanceof z.ZodOptional) inner = inner._def.innerType;
  if (inner instanceof z.ZodString) return wrap({ type: "string" });
  if (inner instanceof z.ZodNumber) return wrap({ type: "number" });
  if (inner instanceof z.ZodBoolean) return wrap({ type: "boolean" });
  if (inner instanceof z.ZodEnum) return wrap({ type: "string", enum: (inner as z.ZodEnum<[string, ...string[]]>).options });
  if (inner instanceof z.ZodArray)
    return wrap({ type: "array", items: zodFieldToJsonSchema(inner._def.type) });
  return wrap({ type: "string" });
}

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error(`[hermes-control] MCP server listening (API=${API_URL})`);
}

main().catch((err) => {
  console.error("[hermes-control] fatal:", err);
  process.exit(1);
});
