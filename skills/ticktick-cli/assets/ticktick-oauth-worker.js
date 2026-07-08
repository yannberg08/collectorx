// Cloudflare Worker 的 TickTick OAuth 服务脚本。
// 仅提供 /authorize 与 /callback 两个端点。

const TICKTICK_AUTH_URL = "https://dida365.com/oauth/authorize";
const TICKTICK_TOKEN_URL = "https://dida365.com/oauth/token";
const DEFAULT_RETURN_TO = "http://127.0.0.1:18921/broker-callback";

/**
 * 返回 JSON 响应。
 * @param {unknown} data 响应数据
 * @param {number} status HTTP 状态码
 * @returns {Response}
 */
function json(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function base64UrlEncode(value) {
  return btoa(value).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

function base64UrlDecode(value) {
  const padded = value.replaceAll("-", "+").replaceAll("_", "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  return atob(padded);
}

function packState({ returnTo, userState }) {
  return base64UrlEncode(JSON.stringify({ return_to: returnTo, state: userState || "" }));
}

function unpackState(raw) {
  if (!raw) return { return_to: DEFAULT_RETURN_TO, state: "" };
  try {
    const data = JSON.parse(base64UrlDecode(raw));
    return {
      return_to: data.return_to || DEFAULT_RETURN_TO,
      state: data.state || "",
    };
  } catch {
    return { return_to: DEFAULT_RETURN_TO, state: raw };
  }
}

function isAllowedReturnTo(value) {
  try {
    const url = new URL(value);
    return (
      url.protocol === "http:" &&
      (url.hostname === "127.0.0.1" || url.hostname === "localhost") &&
      url.port === "18921"
    );
  } catch {
    return false;
  }
}

function postTokenPage(returnTo, tokenData, state) {
  const fields = {
    access_token: tokenData.access_token || "",
    token_type: tokenData.token_type || "Bearer",
    scope: tokenData.scope || "",
    expires_in: tokenData.expires_in || "",
    state: state || "",
  };
  const inputs = Object.entries(fields)
    .map(([key, value]) => `<input type="hidden" name="${escapeHtml(key)}" value="${escapeHtml(value)}">`)
    .join("");
  return new Response(
    `<!doctype html>
<meta charset="utf-8">
<title>滴答清单授权完成</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;max-width:560px;margin:64px auto;padding:0 24px;line-height:1.6;color:#17211b}
.muted{color:#66756b}
</style>
<h1>滴答清单授权完成</h1>
<p class="muted">正在把授权结果写回本机，请稍候...</p>
<form id="f" method="post" action="${escapeHtml(returnTo)}">${inputs}</form>
<script>document.getElementById("f").submit();</script>`,
    {
      status: 200,
      headers: {
        "content-type": "text/html; charset=utf-8",
        "cache-control": "no-store",
      },
    },
  );
}

/**
 * 构造 TickTick OAuth 授权地址。
 * @param {Object} params 参数集合
 * @param {string} params.clientId 客户端 ID
 * @param {string} params.redirectUri 回调地址
 * @param {string} [params.state] 状态值
 * @param {string} [params.scope] 授权范围
 * @param {string} [params.responseType] 响应类型
 * @returns {string}
 */
function buildAuthorizeUrl({
  clientId,
  redirectUri,
  state,
  scope,
  responseType = "code",
}) {
  const url = new URL(TICKTICK_AUTH_URL);
  url.searchParams.set("client_id", clientId);
  url.searchParams.set("redirect_uri", redirectUri);
  url.searchParams.set("response_type", responseType);
  if (scope) {
    url.searchParams.set("scope", scope);
  }
  if (state) {
    url.searchParams.set("state", state);
  }
  return url.toString();
}

/**
 * 使用授权码换取 Token。
 * @param {Object} params 参数集合
 * @param {string} params.code 授权码
 * @param {string} params.clientId 客户端 ID
 * @param {string} params.clientSecret 客户端密钥
 * @param {string} params.redirectUri 回调地址
 * @returns {Promise<{status: number, data: unknown}>}
 */
async function exchangeCodeForToken({
  code,
  clientId,
  clientSecret,
  redirectUri,
}) {
  const body = new URLSearchParams();
  body.set("grant_type", "authorization_code");
  body.set("code", code);
  body.set("client_id", clientId);
  body.set("client_secret", clientSecret);
  body.set("redirect_uri", redirectUri);

  const response = await fetch(TICKTICK_TOKEN_URL, {
    method: "POST",
    headers: {
      "content-type": "application/x-www-form-urlencoded",
    },
    body,
  });

  const text = await response.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    data = { raw: text };
  }

  return { status: response.status, data };
}

/**
 * 读取必需的环境变量。
 * @param {Record<string, string>} env Worker 环境绑定
 * @param {string} key 键名
 * @returns {string}
 */
function getEnvVar(env, key) {
  const value = env?.[key];
  if (!value) {
    throw new Error(`Missing env: ${key}`);
  }
  return value;
}

export default {
  /**
   * Cloudflare Worker 入口。
   * @param {Request} request 请求对象
   * @param {Record<string, string>} env 环境变量
   * @param {ExecutionContext} ctx 执行上下文
   * @returns {Promise<Response>}
   */
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (path === "/authorize") {
      // 启动 OAuth 授权流程：重定向到 TickTick 授权页面。
      const clientId = getEnvVar(env, "TICKTICK_CLIENT_ID");
      const redirectUri = env?.TICKTICK_REDIRECT_URI || `${url.origin}/callback`;
      const returnTo = url.searchParams.get("return_to") || DEFAULT_RETURN_TO;
      if (!isAllowedReturnTo(returnTo)) {
        return json({ ok: false, error: "invalid_return_to" }, 400);
      }
      const state = packState({
        returnTo,
        userState: url.searchParams.get("state") || "",
      });
      const scope = url.searchParams.get("scope") || "";

      const authorizeUrl = buildAuthorizeUrl({
        clientId,
        redirectUri,
        state,
        scope,
      });
      return new Response(null, {
        status: 302,
        headers: {
          location: authorizeUrl,
          "cache-control": "no-store",
        },
      });
    }

    if (path === "/callback") {
      // 处理 OAuth 回调：使用 code 换取 token。
      const code = url.searchParams.get("code");
      const packedState = url.searchParams.get("state");
      const state = unpackState(packedState);
      const error = url.searchParams.get("error");

      if (error) {
        return json({ ok: false, error, state }, 400);
      }

      if (!code) {
        return json({ ok: false, error: "missing_code", state: state.state }, 400);
      }

      const clientId = getEnvVar(env, "TICKTICK_CLIENT_ID");
      const clientSecret = getEnvVar(env, "TICKTICK_CLIENT_SECRET");
      const redirectUri = env?.TICKTICK_REDIRECT_URI || `${url.origin}/callback`;

      const tokenResult = await exchangeCodeForToken({
        code,
        clientId,
        clientSecret,
        redirectUri,
      });

      if (tokenResult.status < 200 || tokenResult.status >= 300) {
        return json(
          {
            error: "token_exchange_failed",
            status: tokenResult.status,
            details: tokenResult.data,
          },
          tokenResult.status,
        );
      }

      const accessToken =
        tokenResult.data &&
        typeof tokenResult.data === "object" &&
        "access_token" in tokenResult.data
          ? tokenResult.data.access_token
          : null;

      if (!accessToken) {
        return json(
          {
            error: "missing_access_token",
            status: tokenResult.status,
            details: tokenResult.data,
          },
          502,
        );
      }

      if (isAllowedReturnTo(state.return_to)) {
        return postTokenPage(state.return_to, tokenResult.data, state.state);
      }

      return json({ access_token: accessToken, state: state.state });
    }

    return json({ ok: false, error: "not_found" }, 404);
  },
};
