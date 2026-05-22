const logEl = document.getElementById("log");
const state = {
  token: "",
  subscription: null,
};

function log(message, data) {
  const line = data ? `${message}\n${JSON.stringify(data, null, 2)}\n` : `${message}\n`;
  logEl.textContent = `${new Date().toISOString()} ${line}\n` + logEl.textContent;
}

function base64UrlToUint8Array(base64Url) {
  const padding = "=".repeat((4 - (base64Url.length % 4)) % 4);
  const base64 = (base64Url + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) output[i] = raw.charCodeAt(i);
  return output;
}

async function fetchJson(url, options = {}) {
  const headers = options.headers || {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const resp = await fetch(url, { ...options, headers });
  const text = await resp.text();
  let body = {};
  try { body = text ? JSON.parse(text) : {}; } catch (_err) { body = { raw: text }; }
  if (!resp.ok) throw new Error(`${resp.status}: ${JSON.stringify(body)}`);
  return body;
}

async function login() {
  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;
  const form = new URLSearchParams();
  form.set("username", username);
  form.set("password", password);
  const tokenBody = await fetchJson("/api/auth/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form,
  });
  state.token = tokenBody.access_token;
  log("JWT получен", { expires_in_seconds: tokenBody.expires_in_seconds });
}

async function subscribe() {
  if (!("serviceWorker" in navigator)) throw new Error("Service Worker не поддерживается");
  if (!("PushManager" in window)) throw new Error("Push API не поддерживается");
  if (!state.token) throw new Error("Сначала выполните логин");

  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error(`Notification permission = ${permission}`);

  const reg = await navigator.serviceWorker.register("/sw.js");
  const keyData = await fetchJson("/api/pwa/public-key");
  if (!keyData.vapid_public_key) throw new Error("Публичный VAPID ключ не настроен на сервере");

  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: base64UrlToUint8Array(keyData.vapid_public_key),
    });
  }
  state.subscription = sub;
  const subJson = sub.toJSON();
  await fetchJson("/api/pwa/subscriptions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      endpoint: sub.endpoint,
      keys: {
        p256dh: subJson.keys.p256dh,
        auth: subJson.keys.auth,
      },
      user_agent: navigator.userAgent,
    }),
  });
  log("Подписка устройства сохранена", { endpoint: sub.endpoint });
}

async function unsubscribe() {
  if (!state.token) throw new Error("Сначала выполните логин");
  const reg = await navigator.serviceWorker.ready;
  const sub = state.subscription || (await reg.pushManager.getSubscription());
  if (!sub) throw new Error("Подписка не найдена");
  await fetchJson("/api/pwa/subscriptions", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ endpoint: sub.endpoint }),
  });
  await sub.unsubscribe();
  state.subscription = null;
  log("Подписка удалена");
}

async function sendTestPush() {
  if (!state.token) throw new Error("Сначала выполните логин");
  const title = document.getElementById("pushTitle").value || "Photofactory test";
  const body = document.getElementById("pushBody").value || "Push";
  const result = await fetchJson("/api/pwa/test-push", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, body }),
  });
  log("Test push отправлен", result);
}

document.getElementById("loginBtn").addEventListener("click", () => login().catch((e) => log("Ошибка login", { error: String(e) })));
document.getElementById("subscribeBtn").addEventListener("click", () => subscribe().catch((e) => log("Ошибка subscribe", { error: String(e) })));
document.getElementById("unsubscribeBtn").addEventListener("click", () => unsubscribe().catch((e) => log("Ошибка unsubscribe", { error: String(e) })));
document.getElementById("sendBtn").addEventListener("click", () => sendTestPush().catch((e) => log("Ошибка test push", { error: String(e) })));
