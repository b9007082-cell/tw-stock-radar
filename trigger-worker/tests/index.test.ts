import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import {
  clearJwksCache,
  createHandler,
  type Env,
} from "../src/index";

const now = Date.parse("2026-07-06T12:00:00.000Z");
let privateKey: CryptoKey;
let publicJwk: JsonWebKey & { kid: string };

const env: Env = {
  GITHUB_TOKEN: "test-token",
  GITHUB_OWNER: "b9007082-cell",
  GITHUB_REPO: "tw-stock-radar",
  GITHUB_WORKFLOW: "update-data.yml",
  GITHUB_REF: "main",
  RADAR_URL: "https://b9007082-cell.github.io/tw-stock-radar/",
  ACCESS_TEAM_DOMAIN: "example.cloudflareaccess.com",
  ACCESS_AUD: "access-audience",
  ALLOWED_EMAIL: "owner@example.com",
};

function base64Url(value: Uint8Array | string): string {
  const bytes =
    typeof value === "string" ? new TextEncoder().encode(value) : value;
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

async function accessToken(email = env.ALLOWED_EMAIL): Promise<string> {
  const header = base64Url(
    JSON.stringify({ alg: "RS256", kid: publicJwk.kid, typ: "JWT" }),
  );
  const claims = base64Url(
    JSON.stringify({
      aud: [env.ACCESS_AUD],
      email,
      exp: Math.floor(now / 1000) + 3600,
      iss: `https://${env.ACCESS_TEAM_DOMAIN}`,
      nbf: Math.floor(now / 1000) - 10,
      sub: "test-user",
    }),
  );
  const content = `${header}.${claims}`;
  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    privateKey,
    new TextEncoder().encode(content),
  );
  return `${content}.${base64Url(new Uint8Array(signature))}`;
}

async function authorizedRequest(
  path: string,
  init: RequestInit = {},
  email = env.ALLOWED_EMAIL,
): Promise<Request> {
  const headers = new Headers(init.headers);
  headers.set("Cf-Access-Jwt-Assertion", await accessToken(email));
  headers.set("Cf-Access-Authenticated-User-Email", email);
  if (init.method === "POST") {
    headers.set("Origin", "https://trigger.example.workers.dev");
  }
  return new Request(`https://trigger.example.workers.dev${path}`, {
    ...init,
    headers,
  });
}

function githubRun(
  overrides: Partial<{
    id: number;
    event: string;
    status: "queued" | "in_progress" | "completed";
    conclusion: string | null;
    created_at: string;
  }> = {},
) {
  return {
    id: 42,
    event: "workflow_dispatch",
    status: "completed",
    conclusion: "success",
    created_at: "2026-07-06T11:00:00.000Z",
    updated_at: "2026-07-06T11:05:00.000Z",
    html_url: "https://github.com/example/actions/runs/42",
    ...overrides,
  };
}

function mockFetch(runs: ReturnType<typeof githubRun>[] = []) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/cdn-cgi/access/certs")) {
      return Response.json({ keys: [publicJwk] });
    }
    if (url.includes("/runs?per_page=10")) {
      return Response.json({ workflow_runs: runs });
    }
    if (url.endsWith("/dispatches") && init?.method === "POST") {
      return new Response(null, { status: 204 });
    }
    return new Response("not found", { status: 404 });
  });
}

beforeAll(async () => {
  const pair = await crypto.subtle.generateKey(
    {
      name: "RSASSA-PKCS1-v1_5",
      modulusLength: 2048,
      publicExponent: new Uint8Array([1, 0, 1]),
      hash: "SHA-256",
    },
    true,
    ["sign", "verify"],
  );
  privateKey = pair.privateKey;
  publicJwk = {
    ...(await crypto.subtle.exportKey("jwk", pair.publicKey)),
    alg: "RS256",
    kid: "test-key",
    use: "sig",
  };
});

afterEach(() => {
  clearJwksCache();
  vi.restoreAllMocks();
});

describe("update trigger worker", () => {
  it("rejects requests without an Access JWT", async () => {
    const handler = createHandler({ fetch: mockFetch(), now: () => now });
    const response = await handler(
      new Request("https://trigger.example.workers.dev/"),
      env,
    );
    expect(response.status).toBe(401);
  });

  it("rejects an authenticated email outside the allowlist", async () => {
    const handler = createHandler({ fetch: mockFetch(), now: () => now });
    const response = await handler(
      await authorizedRequest("/", {}, "other@example.com"),
      env,
    );
    expect(response.status).toBe(403);
  });

  it("serves a protected status page without exposing the GitHub token", async () => {
    const handler = createHandler({ fetch: mockFetch(), now: () => now });
    const response = await handler(await authorizedRequest("/"), env);
    const html = await response.text();
    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Security-Policy")).toContain(
      "frame-ancestors 'none'",
    );
    expect(html).toContain("台股雷達資料更新");
    expect(html).not.toContain(env.GITHUB_TOKEN);
  });

  it("dispatches the exact update workflow once", async () => {
    const fetchMock = mockFetch();
    const handler = createHandler({ fetch: fetchMock, now: () => now });
    const response = await handler(
      await authorizedRequest("/api/dispatch", {
        method: "POST",
        body: "{}",
      }),
      env,
    );
    expect(response.status).toBe(202);
    expect(await response.json()).toMatchObject({ state: "queued" });
    const dispatchCalls = fetchMock.mock.calls.filter(([input]) =>
      String(input).endsWith("/dispatches"),
    );
    expect(dispatchCalls).toHaveLength(1);
    expect(JSON.parse(String(dispatchCalls[0][1]?.body))).toEqual({
      ref: "main",
      inputs: { backfill: "false" },
    });
  });

  it("does not dispatch while an update is already active", async () => {
    const fetchMock = mockFetch([
      githubRun({ status: "in_progress", conclusion: null }),
    ]);
    const handler = createHandler({ fetch: fetchMock, now: () => now });
    const response = await handler(
      await authorizedRequest("/api/dispatch", {
        method: "POST",
        body: "{}",
      }),
      env,
    );
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      state: "already_running",
      run: { status: "in_progress" },
    });
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).endsWith("/dispatches"),
      ),
    ).toBe(false);
  });

  it("enforces the five-minute manual trigger cooldown", async () => {
    const fetchMock = mockFetch([
      githubRun({ created_at: "2026-07-06T11:58:00.000Z" }),
    ]);
    const handler = createHandler({ fetch: fetchMock, now: () => now });
    const response = await handler(
      await authorizedRequest("/api/dispatch", {
        method: "POST",
        body: "{}",
      }),
      env,
    );
    expect(await response.json()).toMatchObject({ state: "cooldown" });
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).endsWith("/dispatches"),
      ),
    ).toBe(false);
  });

  it("tracks an existing scheduled run by id", async () => {
    const scheduled = githubRun({
      id: 99,
      event: "schedule",
      status: "in_progress",
      conclusion: null,
    });
    const handler = createHandler({
      fetch: mockFetch([scheduled]),
      now: () => now,
    });
    const response = await handler(
      await authorizedRequest("/api/status?run_id=99"),
      env,
    );
    expect(await response.json()).toMatchObject({
      state: "in_progress",
      run: { id: 99, event: "schedule" },
    });
  });
});
