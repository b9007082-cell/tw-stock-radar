export interface Env {
  GITHUB_TOKEN: string;
  GITHUB_OWNER: string;
  GITHUB_REPO: string;
  GITHUB_WORKFLOW: string;
  GITHUB_REF: string;
  RADAR_URL: string;
  ACCESS_TEAM_DOMAIN: string;
  ACCESS_AUD: string;
  ALLOWED_EMAIL: string;
}

interface AccessHeader {
  alg?: string;
  kid?: string;
}

interface AccessClaims {
  aud?: string | string[];
  email?: string;
  exp?: number;
  iss?: string;
  nbf?: number;
  sub?: string;
}

interface AccessJwk extends JsonWebKey {
  kid?: string;
}

interface WorkflowRun {
  id: number;
  event: string;
  status: "queued" | "in_progress" | "completed";
  conclusion: string | null;
  created_at: string;
  updated_at: string;
  html_url: string;
}

interface WorkflowRunsResponse {
  workflow_runs: WorkflowRun[];
}

interface RuntimeDependencies {
  fetch: typeof fetch;
  now: () => number;
}

interface CachedJwks {
  expiresAt: number;
  keys: AccessJwk[];
}

const defaultDependencies: RuntimeDependencies = {
  fetch: globalThis.fetch.bind(globalThis),
  now: () => Date.now(),
};

const jwksCache = new Map<string, CachedJwks>();
const encoder = new TextEncoder();
const decoder = new TextDecoder();
const githubApiVersion = "2022-11-28";
const cooldownMilliseconds = 5 * 60 * 1000;

class HttpError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "application/json; charset=utf-8",
      "Referrer-Policy": "no-referrer",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

function base64UrlBytes(value: string): Uint8Array<ArrayBuffer> {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function decodeJwtPart<T>(value: string): T {
  return JSON.parse(decoder.decode(base64UrlBytes(value))) as T;
}

function accessHost(teamDomain: string): string {
  const normalized = teamDomain
    .trim()
    .replace(/^https?:\/\//, "")
    .replace(/\/+$/, "");
  return normalized.includes(".")
    ? normalized
    : `${normalized}.cloudflareaccess.com`;
}

async function getAccessKeys(
  host: string,
  dependencies: RuntimeDependencies,
): Promise<AccessJwk[]> {
  const cached = jwksCache.get(host);
  if (cached && cached.expiresAt > dependencies.now()) {
    return cached.keys;
  }
  const response = await dependencies.fetch(
    `https://${host}/cdn-cgi/access/certs`,
    { headers: { Accept: "application/json" } },
  );
  if (!response.ok) {
    throw new HttpError("無法取得Cloudflare Access驗證金鑰。", 503);
  }
  const payload = (await response.json()) as { keys?: AccessJwk[] };
  if (!Array.isArray(payload.keys) || payload.keys.length === 0) {
    throw new HttpError("Cloudflare Access驗證金鑰格式錯誤。", 503);
  }
  jwksCache.set(host, {
    keys: payload.keys,
    expiresAt: dependencies.now() + 5 * 60 * 1000,
  });
  return payload.keys;
}

async function verifyAccess(
  request: Request,
  env: Env,
  dependencies: RuntimeDependencies,
): Promise<AccessClaims> {
  const token = request.headers.get("Cf-Access-Jwt-Assertion");
  if (!token) {
    throw new HttpError("缺少Cloudflare Access身份憑證。", 401);
  }
  const parts = token.split(".");
  if (parts.length !== 3) {
    throw new HttpError("Cloudflare Access身份憑證格式錯誤。", 401);
  }
  const [encodedHeader, encodedClaims, encodedSignature] = parts;
  const header = decodeJwtPart<AccessHeader>(encodedHeader);
  const claims = decodeJwtPart<AccessClaims>(encodedClaims);
  if (header.alg !== "RS256" || !header.kid) {
    throw new HttpError("不支援的Access簽章演算法。", 401);
  }

  const host = accessHost(env.ACCESS_TEAM_DOMAIN);
  const keys = await getAccessKeys(host, dependencies);
  const jwk = keys.find((candidate) => candidate.kid === header.kid);
  if (!jwk) {
    throw new HttpError("找不到Access簽章金鑰。", 401);
  }
  const publicKey = await crypto.subtle.importKey(
    "jwk",
    jwk,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["verify"],
  );
  const validSignature = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    publicKey,
    base64UrlBytes(encodedSignature),
    encoder.encode(`${encodedHeader}.${encodedClaims}`),
  );
  if (!validSignature) {
    throw new HttpError("Access身份憑證簽章無效。", 401);
  }

  const nowSeconds = Math.floor(dependencies.now() / 1000);
  const expectedIssuer = `https://${host}`;
  const audiences = Array.isArray(claims.aud)
    ? claims.aud
    : claims.aud
      ? [claims.aud]
      : [];
  if (
    claims.iss?.replace(/\/+$/, "") !== expectedIssuer ||
    !audiences.includes(env.ACCESS_AUD) ||
    typeof claims.exp !== "number" ||
    claims.exp < nowSeconds - 60 ||
    (typeof claims.nbf === "number" && claims.nbf > nowSeconds + 60)
  ) {
    throw new HttpError("Access身份憑證的issuer、audience或時間無效。", 401);
  }

  const email = claims.email?.trim().toLowerCase();
  const allowedEmail = env.ALLOWED_EMAIL.trim().toLowerCase();
  const accessHeaderEmail = request.headers
    .get("Cf-Access-Authenticated-User-Email")
    ?.trim()
    .toLowerCase();
  if (
    !email ||
    email !== allowedEmail ||
    (accessHeaderEmail && accessHeaderEmail !== email)
  ) {
    throw new HttpError("此Email沒有觸發更新的權限。", 403);
  }
  return claims;
}

function githubHeaders(env: Env): HeadersInit {
  return {
    Accept: "application/vnd.github+json",
    Authorization: `Bearer ${env.GITHUB_TOKEN}`,
    "Content-Type": "application/json",
    "User-Agent": "tw-stock-radar-update-trigger",
    "X-GitHub-Api-Version": githubApiVersion,
  };
}

function workflowUrl(env: Env, suffix = ""): string {
  const owner = encodeURIComponent(env.GITHUB_OWNER);
  const repo = encodeURIComponent(env.GITHUB_REPO);
  const workflow = encodeURIComponent(env.GITHUB_WORKFLOW);
  return `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflow}${suffix}`;
}

async function workflowRuns(
  env: Env,
  dependencies: RuntimeDependencies,
): Promise<WorkflowRun[]> {
  const response = await dependencies.fetch(
    workflowUrl(env, "/runs?per_page=10"),
    { headers: githubHeaders(env) },
  );
  if (!response.ok) {
    throw new HttpError(
      `GitHub狀態查詢失敗（${response.status}）。請檢查PAT權限或期限。`,
      502,
    );
  }
  const payload = (await response.json()) as WorkflowRunsResponse;
  return Array.isArray(payload.workflow_runs) ? payload.workflow_runs : [];
}

function publicRun(run: WorkflowRun) {
  return {
    id: run.id,
    event: run.event,
    status: run.status,
    conclusion: run.conclusion,
    created_at: run.created_at,
    updated_at: run.updated_at,
    html_url: run.html_url,
  };
}

async function dispatchWorkflow(
  request: Request,
  env: Env,
  dependencies: RuntimeDependencies,
): Promise<Response> {
  const expectedOrigin = new URL(request.url).origin;
  if (request.headers.get("Origin") !== expectedOrigin) {
    return jsonResponse({ error: "拒絕跨來源觸發。" }, 403);
  }

  const runs = await workflowRuns(env, dependencies);
  const active = runs.find(
    (run) => run.status === "queued" || run.status === "in_progress",
  );
  if (active) {
    return jsonResponse({
      state: "already_running",
      run: publicRun(active),
    });
  }

  const latestManual = runs.find((run) => run.event === "workflow_dispatch");
  if (
    latestManual &&
    dependencies.now() - Date.parse(latestManual.created_at) <
      cooldownMilliseconds
  ) {
    return jsonResponse({
      state: "cooldown",
      run: publicRun(latestManual),
    });
  }

  const requestedAt = new Date(dependencies.now()).toISOString();
  const response = await dependencies.fetch(workflowUrl(env, "/dispatches"), {
    method: "POST",
    headers: githubHeaders(env),
    body: JSON.stringify({
      ref: env.GITHUB_REF,
      inputs: { backfill: "false" },
    }),
  });
  if (response.status !== 204) {
    throw new HttpError(
      `GitHub觸發失敗（${response.status}）。請檢查Actions權限。`,
      502,
    );
  }
  return jsonResponse(
    { state: "queued", requested_at: requestedAt, run: null },
    202,
  );
}

async function workflowStatus(
  url: URL,
  env: Env,
  dependencies: RuntimeDependencies,
): Promise<Response> {
  const runId = Number(url.searchParams.get("run_id"));
  const sinceRaw = url.searchParams.get("since");
  const since = sinceRaw ? Date.parse(sinceRaw) : Number.NaN;
  const runs = await workflowRuns(env, dependencies);
  const matching =
    Number.isSafeInteger(runId) && runId > 0
      ? runs.find((run) => run.id === runId)
      : Number.isFinite(since)
        ? runs.find(
            (run) =>
              run.event === "workflow_dispatch" &&
              Date.parse(run.created_at) >= since - 60_000,
          )
        : runs[0];
  return jsonResponse(
    matching
      ? { state: matching.status, run: publicRun(matching) }
      : { state: "pending", run: null },
  );
}

function escapeHtml(value: string): string {
  return value.replace(
    /[&<>"']/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[character] ?? character,
  );
}

function randomNonce(): string {
  const bytes = new Uint8Array(18);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}

function statusPage(env: Env): Response {
  const nonce = randomNonce();
  const radarUrl = escapeHtml(env.RADAR_URL);
  const html = `<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>台股雷達資料更新</title>
  <style nonce="${nonce}">
    :root{color-scheme:dark;font-family:ui-sans-serif,system-ui,sans-serif;background:#07111f;color:#e2e8f0}
    body{min-height:100vh;margin:0;display:grid;place-items:center;padding:20px;box-sizing:border-box}
    main{width:min(560px,100%);border:1px solid #334155;border-radius:20px;background:#0f172acc;padding:28px;box-sizing:border-box}
    h1{margin:0 0 10px;font-size:24px}p{color:#94a3b8;line-height:1.7}
    #state{margin:22px 0;padding:16px;border-radius:14px;background:#02061780;border:1px solid #1e293b}
    .label{font-weight:700;color:#6ee7b7}.error{color:#fda4af}.success{color:#6ee7b7}
    a,button{display:inline-flex;border-radius:10px;padding:10px 14px;font-weight:700;text-decoration:none}
    a{color:#020617;background:#6ee7b7}button{margin-left:8px;color:#cbd5e1;background:#1e293b;border:0;cursor:pointer}
    small{display:block;margin-top:18px;color:#64748b;line-height:1.6}
  </style>
</head>
<body>
  <main>
    <h1>台股雷達資料更新</h1>
    <p>系統會抓取最新盤後資料、重新選股、執行測試並部署網站。</p>
    <div id="state"><span class="label">準備觸發更新…</span></div>
    <a href="${radarUrl}">返回台股雷達</a>
    <button id="retry" type="button" hidden>重新嘗試</button>
    <small>執行中的更新不會重複啟動。GitHub Actions排隊可能需要數分鐘。</small>
  </main>
  <script nonce="${nonce}">
    const state = document.getElementById("state");
    const retry = document.getElementById("retry");
    let requestedAt = null;
    let runId = null;
    let attempts = 0;
    const render = (message, kind = "") => {
      state.innerHTML = "";
      const text = document.createElement("span");
      text.className = kind;
      text.textContent = message;
      state.appendChild(text);
    };
    const poll = async () => {
      if (attempts++ > 120) {
        render("更新仍在執行，請稍後到GitHub Actions確認。");
        return;
      }
      const query = runId
        ? "?run_id=" + encodeURIComponent(runId)
        : requestedAt
          ? "?since=" + encodeURIComponent(requestedAt)
          : "";
      const response = await fetch("./api/status" + query, { cache: "no-store" });
      const payload = await response.json();
      const run = payload.run;
      if (payload.state === "completed") {
        if (run && run.conclusion === "success") {
          render("更新成功。網站部署通常會再需要1至2分鐘。", "success");
        } else {
          render("更新失敗。請開啟GitHub Actions查看執行紀錄。", "error");
          if (run && run.html_url) {
            const link = document.createElement("a");
            link.href = run.html_url;
            link.target = "_blank";
            link.rel = "noopener";
            link.textContent = "查看錯誤";
            state.appendChild(document.createElement("br"));
            state.appendChild(link);
          }
          retry.hidden = false;
        }
        return;
      }
      render(payload.state === "in_progress" ? "更新執行中…" : "更新已排隊，等待GitHub執行…");
      setTimeout(poll, 5000);
    };
    const trigger = async () => {
      retry.hidden = true;
      render("正在送出更新要求…");
      try {
        const response = await fetch("./api/dispatch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}"
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "觸發失敗");
        requestedAt = payload.requested_at || (payload.run && payload.run.created_at) || null;
        runId = payload.run && payload.run.id ? payload.run.id : null;
        await poll();
      } catch (error) {
        render(error instanceof Error ? error.message : "觸發失敗", "error");
        retry.hidden = false;
      }
    };
    retry.addEventListener("click", trigger);
    trigger();
  </script>
</body>
</html>`;
  return new Response(html, {
    headers: {
      "Cache-Control": "no-store",
      "Content-Security-Policy": `default-src 'none'; script-src 'nonce-${nonce}'; style-src 'nonce-${nonce}'; connect-src 'self'; img-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'`,
      "Content-Type": "text/html; charset=utf-8",
      "Referrer-Policy": "no-referrer",
      "X-Content-Type-Options": "nosniff",
      "X-Frame-Options": "DENY",
    },
  });
}

async function handleRequest(
  request: Request,
  env: Env,
  dependencies: RuntimeDependencies,
): Promise<Response> {
  try {
    await verifyAccess(request, env, dependencies);
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/") {
      return statusPage(env);
    }
    if (request.method === "POST" && url.pathname === "/api/dispatch") {
      return await dispatchWorkflow(request, env, dependencies);
    }
    if (request.method === "GET" && url.pathname === "/api/status") {
      return await workflowStatus(url, env, dependencies);
    }
    return jsonResponse({ error: "找不到此端點。" }, 404);
  } catch (error) {
    if (error instanceof HttpError) {
      return jsonResponse({ error: error.message }, error.status);
    }
    return jsonResponse({ error: "更新服務發生未預期錯誤。" }, 500);
  }
}

export function createHandler(
  dependencies: RuntimeDependencies = defaultDependencies,
) {
  return (request: Request, env: Env) =>
    handleRequest(request, env, dependencies);
}

export function clearJwksCache() {
  jwksCache.clear();
}

export default {
  fetch(request: Request, env: Env): Promise<Response> {
    return handleRequest(request, env, defaultDependencies);
  },
};
