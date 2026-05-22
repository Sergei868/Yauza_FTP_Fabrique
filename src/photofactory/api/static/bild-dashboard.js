const state = {
  token: localStorage.getItem("pf_token") || "",
  pollTimer: null,
  batchCache: new Map(),
};

const statusEl = document.getElementById("status");
const metaEl = document.getElementById("meta");
const notificationsEl = document.getElementById("notifications");
const batchesEl = document.getElementById("batches");
const autoYandexToggleEl = document.getElementById("autoYandexToggle");

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.style.color = isError ? "#b00020" : "#222";
}

function getHeaders(extra = {}) {
  const headers = { ...extra };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  return headers;
}

async function apiJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: getHeaders(options.headers || {}),
  });
  const text = await response.text();
  let body = {};
  try { body = text ? JSON.parse(text) : {}; } catch (_err) { body = { raw: text }; }
  if (!response.ok) {
    throw new Error(`${response.status}: ${JSON.stringify(body)}`);
  }
  return body;
}

function renderNotifications(items) {
  const unread = items.filter((item) => item.status !== "read").length;
  metaEl.textContent = `Уведомлений: ${items.length} | Непрочитанных: ${unread}`;
  notificationsEl.innerHTML = "";
  for (const item of items) {
    const div = document.createElement("div");
    div.className = "notif";
    div.innerHTML = `
      <div><b>${item.title}</b> <span class="mono">(${item.channel})</span></div>
      <div>${item.message}</div>
      <div class="mono">${item.created_at}</div>
    `;
    notificationsEl.appendChild(div);
  }
}

async function fetchNotifications() {
  const items = await apiJson("/api/notifications?limit=20");
  renderNotifications(items);
}

function esc(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function formatBatchMeta(batch) {
  return `${batch.photographer}, ${new Date(batch.captured_at).toLocaleString()}, ${batch.file_count} снимков, ${batch.broken_files_count} битых, #${batch.daily_sequence} за сутки`;
}

function renderBatchGallery(batch, detail) {
  const images = detail.photos.map((photo) => `<img src="${photo.image_url}" alt="${esc(photo.filename)}" loading="lazy" />`).join("");
  return `
    <div class="batch-card" id="batch-${batch.id}">
      <div class="batch-header"><b>${esc(formatBatchMeta(batch))}</b></div>
      <div class="row">
        <button data-action="download" data-batch-id="${batch.id}">Скачать пакет</button>
        <button data-action="yadisk" data-batch-id="${batch.id}">Загрузить на Я.Диск</button>
      </div>
      <div class="mono">${esc(batch.archive_name)}</div>
      <div class="gallery">${images || '<span class="muted">В пачке нет валидных JPEG</span>'}</div>
    </div>
  `;
}

async function fetchBatchDetail(batchId) {
  if (state.batchCache.has(batchId)) return state.batchCache.get(batchId);
  const detail = await apiJson(`/api/batches/${batchId}`);
  state.batchCache.set(batchId, detail);
  return detail;
}

async function fetchBatchesAndRender() {
  state.batchCache.clear();
  const batches = await apiJson("/api/batches?limit=20");
  if (!batches.length) {
    batchesEl.innerHTML = '<div class="muted">Пока нет пачек.</div>';
    return;
  }
  const rendered = [];
  for (const batch of batches) {
    const detail = await fetchBatchDetail(batch.id);
    rendered.push(renderBatchGallery(batch, detail));
  }
  batchesEl.innerHTML = rendered.join("");
}

async function login() {
  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;
  const form = new URLSearchParams();
  form.set("username", username);
  form.set("password", password);
  const tokenBody = await apiJson("/api/auth/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form,
  });
  state.token = tokenBody.access_token;
  localStorage.setItem("pf_token", state.token);
  setStatus(`JWT получен, TTL ${tokenBody.expires_in_seconds}s`);
  await fetchNotifications();
  await loadAutoYandexMode();
  await fetchBatchesAndRender();
  startPolling();
}

function logout() {
  state.token = "";
  localStorage.removeItem("pf_token");
  stopPolling();
  notificationsEl.innerHTML = "";
  batchesEl.innerHTML = "";
  autoYandexToggleEl.checked = false;
  metaEl.textContent = "";
  setStatus("Выход выполнен");
}

function startPolling() {
  stopPolling();
  state.pollTimer = setInterval(async () => {
    try {
      await fetchNotifications();
      await fetchBatchesAndRender();
    } catch (err) {
      setStatus(`Ошибка polling: ${String(err)}`, true);
    }
  }, 10000);
}

function stopPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

function base64UrlToUint8Array(base64Url) {
  const padding = "=".repeat((4 - (base64Url.length % 4)) % 4);
  const base64 = (base64Url + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) output[i] = raw.charCodeAt(i);
  return output;
}

async function enablePush() {
  if (!state.token) throw new Error("Сначала выполните вход");
  if (!("serviceWorker" in navigator)) throw new Error("Service Worker не поддерживается");
  if (!("PushManager" in window)) throw new Error("Push API не поддерживается");

  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error(`Notification permission: ${permission}`);

  const reg = await navigator.serviceWorker.register("/sw.js");
  const keyData = await apiJson("/api/pwa/public-key");
  if (!keyData.vapid_public_key) throw new Error("VAPID public key не настроен");

  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: base64UrlToUint8Array(keyData.vapid_public_key),
    });
  }
  const subJson = sub.toJSON();
  await apiJson("/api/pwa/subscriptions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      endpoint: sub.endpoint,
      keys: { p256dh: subJson.keys.p256dh, auth: subJson.keys.auth },
      user_agent: navigator.userAgent,
    }),
  });
  setStatus("Push включен на этом устройстве");
}

async function disablePush() {
  if (!state.token) throw new Error("Сначала выполните вход");
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  if (!sub) {
    setStatus("Подписка не найдена");
    return;
  }
  await apiJson("/api/pwa/subscriptions", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ endpoint: sub.endpoint }),
  });
  await sub.unsubscribe();
  setStatus("Push отключен");
}

async function sendTestPush() {
  if (!state.token) throw new Error("Сначала выполните вход");
  const result = await apiJson("/api/pwa/test-push", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "Bild dashboard", body: "Тестовое push-уведомление" }),
  });
  setStatus(`Test push: sent=${result.sent}, failed=${result.failed}`);
}

async function markRead() {
  if (!state.token) throw new Error("Сначала выполните вход");
  const result = await apiJson("/api/notifications/mark-read", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode: "all" }),
  });
  setStatus(`Помечено как прочитано: ${result.updated}`);
  await fetchNotifications();
}

async function triggerRealBatch() {
  if (!state.token) throw new Error("Сначала выполните вход");
  const suffix = Date.now().toString().slice(-6);
  const result = await apiJson("/api/dev/smoke-batch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      photographer: "BildSmoke",
      filename: `BILD-${suffix}.jpg`,
      content: "bild-dashboard-smoke",
    }),
  });
  setStatus(`Тестовая пачка поставлена: ${result.file_path}`);
}

async function loadAutoYandexMode() {
  if (!state.token) return;
  const mode = await apiJson("/api/yandex/auto-upload");
  autoYandexToggleEl.checked = !!mode.enabled;
}

async function updateAutoYandexMode(enabled) {
  if (!state.token) throw new Error("Сначала выполните вход");
  const result = await apiJson("/api/yandex/auto-upload", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  autoYandexToggleEl.checked = !!result.enabled;
  setStatus(`Авто Я.Диск: ${result.enabled ? "включен" : "выключен"}`);
}

function downloadBatch(batchId) {
  if (!state.token) throw new Error("Сначала выполните вход");
  const url = `/api/batches/${batchId}/download`;
  fetch(url, { headers: getHeaders() })
    .then(async (response) => {
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `download failed ${response.status}`);
      }
      const blob = await response.blob();
      const contentDisposition = response.headers.get("Content-Disposition") || "";
      const match = /filename="([^"]+)"/.exec(contentDisposition);
      const filename = match ? match[1] : `batch-${batchId}.zip`;
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(objectUrl);
      setStatus(`Скачан пакет: ${filename}`);
    })
    .catch((err) => setStatus(`Ошибка скачивания: ${String(err)}`, true));
}

async function uploadBatchToYandex(batchId) {
  if (!state.token) throw new Error("Сначала выполните вход");
  const result = await apiJson(`/api/batches/${batchId}/upload-yandex`, {
    method: "POST",
  });
  setStatus(`На Я.Диск выгружено файлов: ${result.uploaded_files}, папка: ${result.remote_path}`);
}

document.getElementById("loginBtn").addEventListener("click", () => login().catch((e) => setStatus(String(e), true)));
document.getElementById("logoutBtn").addEventListener("click", logout);
document.getElementById("refreshBtn").addEventListener("click", () => fetchNotifications().catch((e) => setStatus(String(e), true)));
document.getElementById("enablePushBtn").addEventListener("click", () => enablePush().catch((e) => setStatus(String(e), true)));
document.getElementById("disablePushBtn").addEventListener("click", () => disablePush().catch((e) => setStatus(String(e), true)));
document.getElementById("testPushBtn").addEventListener("click", () => sendTestPush().catch((e) => setStatus(String(e), true)));
document.getElementById("realBatchBtn").addEventListener("click", () => triggerRealBatch().catch((e) => setStatus(String(e), true)));
document.getElementById("markReadBtn").addEventListener("click", () => markRead().catch((e) => setStatus(String(e), true)));
autoYandexToggleEl.addEventListener("change", (event) => {
  const enabled = !!event.target.checked;
  updateAutoYandexMode(enabled).catch((e) => setStatus(String(e), true));
});
batchesEl.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const action = target.getAttribute("data-action");
  const batchId = target.getAttribute("data-batch-id");
  if (!action || !batchId) return;
  if (action === "download") {
    downloadBatch(batchId);
    return;
  }
  if (action === "yadisk") {
    uploadBatchToYandex(batchId).catch((e) => setStatus(String(e), true));
  }
});

if (state.token) {
  Promise.all([fetchNotifications(), loadAutoYandexMode(), fetchBatchesAndRender()])
    .then(startPolling)
    .then(() => setStatus("Сессия восстановлена, polling активен"))
    .catch((e) => setStatus(`Нужен вход: ${String(e)}`, true));
}
