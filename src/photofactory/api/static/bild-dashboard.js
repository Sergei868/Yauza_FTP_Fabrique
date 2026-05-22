const state = {
  token: localStorage.getItem("pf_token") || "",
  pollTimer: null,
  batchCache: new Map(),
  allBatches: [],
  actionsInProgress: new Set(),
  imageObjectUrls: new Map(),
  originalObjectUrls: new Map(),
  incomingPhotographers: [],
  activeTab: "packages",
  lastRenderSignature: "",
  lightbox: null,
};

const statusEl = document.getElementById("status");
const metaEl = document.getElementById("meta");
const notificationsEl = document.getElementById("notifications");
const batchesEl = document.getElementById("batches");
const batchStatsEl = document.getElementById("batchStats");
const autoYandexToggleEl = document.getElementById("autoYandexToggle");
const searchInputEl = document.getElementById("searchInput");
const photographerFilterEl = document.getElementById("photographerFilter");
const dateFromEl = document.getElementById("dateFrom");
const dateToEl = document.getElementById("dateTo");
const refreshPackagesBtnEl = document.getElementById("refreshPackagesBtn");
const cleanupProcessedBtnEl = document.getElementById("cleanupProcessedBtn");
const tabButtons = [...document.querySelectorAll("[data-tab-target]")];
const tabPanels = [...document.querySelectorAll("[data-tab-panel]")];
const lightboxEl = document.getElementById("lightbox");
const lightboxImageEl = document.getElementById("lightboxImage");
const lightboxTitleEl = document.getElementById("lightboxTitle");
const lightboxCloseBtnEl = document.getElementById("lightboxCloseBtn");
const lightboxDownloadBtnEl = document.getElementById("lightboxDownloadBtn");
const lightboxPrevBtnEl = document.getElementById("lightboxPrevBtn");
const lightboxNextBtnEl = document.getElementById("lightboxNextBtn");
const lightboxCounterEl = document.getElementById("lightboxCounter");

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.className = `mono status ${isError ? "error" : "ok"}`;
}

function clearSessionState() {
  state.token = "";
  localStorage.removeItem("pf_token");
  stopPolling();
}

function handleAuthExpired() {
  clearSessionState();
  setActiveTab("settings");
  setStatus("Сессия истекла или недействительна. Войдите снова.", true);
}

function setActiveTab(tabId) {
  state.activeTab = tabId;
  for (const btn of tabButtons) {
    const active = btn.getAttribute("data-tab-target") === tabId;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  }
  for (const panel of tabPanels) {
    const active = panel.getAttribute("data-tab-panel") === tabId;
    panel.classList.toggle("active", active);
  }
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
    if (response.status === 401) {
      handleAuthExpired();
    }
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
  return `${new Date(batch.captured_at).toLocaleString()} | ${batch.file_count} снимков | ${batch.broken_files_count} битых | #${batch.daily_sequence} за сутки`;
}

function actionKey(action, batchId) {
  return `${action}:${batchId}`;
}

function withActionState(action, batchId, running) {
  const key = actionKey(action, batchId);
  if (running) state.actionsInProgress.add(key);
  else state.actionsInProgress.delete(key);
}

function isActionRunning(action, batchId) {
  return state.actionsInProgress.has(actionKey(action, batchId));
}

function renderBatchGallery(batch, detail) {
  const images = detail.photos
    .map(
      (photo, index) => `<button class="thumb-btn" type="button"
        data-action="open-image"
        data-batch-id="${esc(batch.id)}"
        data-photo-index="${index}"
        data-photo-id="${esc(photo.id)}"
        data-original-src="${esc(photo.image_url)}"
        data-filename="${esc(photo.filename)}"
      ><img
        data-photo-id="${esc(photo.id)}"
        data-auth-src="${esc(photo.thumbnail_url || photo.image_url)}"
        alt="${esc(photo.filename)}"
        loading="lazy"
        title="${esc(photo.filename)}"
      /></button>`,
    )
    .join("");
  const downloadBusy = isActionRunning("download", batch.id);
  const yandexBusy = isActionRunning("yadisk", batch.id);
  return `
    <div class="batch-card" id="batch-${batch.id}">
      <div class="batch-top">
        <div>
          <div class="batch-title">${esc(batch.photographer)}</div>
          <div class="batch-sub">${esc(formatBatchMeta(batch))}</div>
        </div>
        <div class="batch-badges">
          <span class="badge">Пачка: ${esc(batch.batch_key)}</span>
          <span class="badge">ZIP: ${esc(batch.archive_name)}</span>
        </div>
      </div>
      <div class="row">
        <button data-action="download" data-batch-id="${batch.id}" ${downloadBusy ? "disabled" : ""}>${downloadBusy ? "Скачивание..." : "Скачать пакет"}</button>
        <button data-action="yadisk" data-batch-id="${batch.id}" ${yandexBusy ? "disabled" : ""}>${yandexBusy ? "Загрузка..." : "Загрузить на Я.Диск"}</button>
      </div>
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
  const previousById = new Map(state.allBatches.map((batch) => [batch.id, batch]));
  const [batches, incomingPhotographers] = await Promise.all([
    apiJson("/api/batches?limit=50"),
    fetchIncomingPhotographers(),
  ]);
  state.allBatches = batches;
  state.incomingPhotographers = incomingPhotographers;
  syncPhotographerFilterOptions();

  const filtered = applyBatchFilters(batches);
  renderBatchStats(batches, filtered);
  const renderSignature = JSON.stringify({
    ids: filtered.map((item) => item.id),
    status: filtered.map((item) => item.status),
    files: filtered.map((item) => item.file_count),
    broken: filtered.map((item) => item.broken_files_count),
    f: [
      searchInputEl.value.trim(),
      photographerFilterEl.value,
      dateFromEl.value,
      dateToEl.value,
    ],
  });
  if (!filtered.length) {
    batchesEl.innerHTML = '<div class="muted">Пока нет пачек.</div>';
    state.lastRenderSignature = renderSignature;
    return;
  }
  if (renderSignature === state.lastRenderSignature) {
    return;
  }
  const rendered = [];
  for (const batch of filtered) {
    const prev = previousById.get(batch.id);
    const changed = !prev || prev.file_count !== batch.file_count || prev.broken_files_count !== batch.broken_files_count;
    if (changed) state.batchCache.delete(batch.id);
    const detail = await fetchBatchDetail(batch.id);
    rendered.push(renderBatchGallery(batch, detail));
  }
  batchesEl.innerHTML = rendered.join("");
  state.lastRenderSignature = renderSignature;
  await hydrateBatchImages();
}

async function hydrateBatchImages() {
  const targets = [...batchesEl.querySelectorAll("img[data-photo-id][data-auth-src]")];
  const queue = targets.slice();
  const workers = [];
  const workerCount = Math.min(6, queue.length);
  async function loadSingle(imgEl) {
    const photoId = imgEl.getAttribute("data-photo-id") || "";
    const source = imgEl.getAttribute("data-auth-src") || "";
    if (!photoId || !source) return;
    const cached = state.imageObjectUrls.get(photoId);
    if (cached) {
      imgEl.src = cached;
      return;
    }
    try {
      const response = await fetch(source, { headers: getHeaders() });
      if (!response.ok) throw new Error(`image fetch failed ${response.status}`);
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      state.imageObjectUrls.set(photoId, objectUrl);
      imgEl.src = objectUrl;
    } catch (_err) {
      imgEl.alt = `${imgEl.alt || "photo"} (не удалось загрузить)`;
    }
  }
  for (let i = 0; i < workerCount; i += 1) {
    workers.push((async () => {
      while (queue.length) {
        const imgEl = queue.shift();
        if (!imgEl) break;
        await loadSingle(imgEl);
      }
    })());
  }
  await Promise.all(workers);
}

function syncPhotographerFilterOptions() {
  const current = photographerFilterEl.value;
  const names = state.incomingPhotographers.map((item) => item.folder_name).sort((a, b) => a.localeCompare(b));
  photographerFilterEl.innerHTML = '<option value="">Все фотографы</option>';
  for (const name of names) {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    photographerFilterEl.appendChild(option);
  }
  if (names.includes(current)) photographerFilterEl.value = current;
}

async function fetchIncomingPhotographers() {
  const items = await apiJson("/api/incoming/photographers");
  return Array.isArray(items) ? items : [];
}

function renderBatchStats(allBatches, filteredBatches) {
  const totalBroken = filteredBatches.reduce((acc, item) => acc + item.broken_files_count, 0);
  const chips = [
    `Всего пачек: ${allBatches.length}`,
    `Показано: ${filteredBatches.length}`,
    `Битых в фильтре: ${totalBroken}`,
  ];
  batchStatsEl.innerHTML = chips.map((item) => `<span class="chip">${esc(item)}</span>`).join("");
}

function isInDateRange(batch, fromRaw, toRaw) {
  const d = new Date(batch.captured_at);
  if (Number.isNaN(d.getTime())) return false;
  if (fromRaw) {
    const from = new Date(`${fromRaw}T00:00:00`);
    if (d < from) return false;
  }
  if (toRaw) {
    const to = new Date(`${toRaw}T23:59:59`);
    if (d > to) return false;
  }
  return true;
}

function applyBatchFilters(batches) {
  const searchRaw = searchInputEl.value.trim().toLowerCase();
  const photographerRaw = photographerFilterEl.value.trim().toLowerCase();
  const fromRaw = dateFromEl.value;
  const toRaw = dateToEl.value;
  return batches.filter((batch) => {
    if (photographerRaw && batch.photographer.toLowerCase() !== photographerRaw) return false;
    if (!isInDateRange(batch, fromRaw, toRaw)) return false;
    if (!searchRaw) return true;
    const haystack = `${batch.photographer} ${batch.batch_key} ${batch.archive_name}`.toLowerCase();
    return haystack.includes(searchRaw);
  });
}

async function cleanupProcessedBatches() {
  if (!state.token) throw new Error("Сначала выполните вход");
  const result = await apiJson("/api/batches/cleanup-processed", { method: "POST" });
  setStatus(`Скрыто старых/обработанных пачек: ${result.updated}`);
  await fetchBatchesAndRender();
}

async function fetchBlobObjectUrl(url, cacheMap, cacheKey) {
  const cached = cacheMap.get(cacheKey);
  if (cached) return cached;
  const response = await fetch(url, { headers: getHeaders() });
  if (!response.ok) throw new Error(`image fetch failed ${response.status}`);
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  cacheMap.set(cacheKey, objectUrl);
  return objectUrl;
}

async function openLightbox(photoId, originalSrc, filename) {
  if (!photoId || !originalSrc) return;
  if (!state.token) throw new Error("Сначала выполните вход");
  lightboxTitleEl.textContent = filename || photoId;
  lightboxImageEl.removeAttribute("src");
  lightboxImageEl.alt = filename || "Оригинал";
  lightboxEl.classList.add("active");
  lightboxEl.setAttribute("aria-hidden", "false");
  const objectUrl = await fetchBlobObjectUrl(originalSrc, state.originalObjectUrls, photoId);
  lightboxImageEl.src = objectUrl;
  state.lightbox = {
    photos: [{ photoId, originalSrc, filename }],
    index: 0,
  };
  updateLightboxControls();
}

function closeLightbox() {
  lightboxEl.classList.remove("active");
  lightboxEl.setAttribute("aria-hidden", "true");
  lightboxImageEl.removeAttribute("src");
  state.lightbox = null;
}

async function openLightboxAt(photos, index) {
  if (!photos.length) return;
  const safeIndex = Math.max(0, Math.min(index, photos.length - 1));
  const current = photos[safeIndex];
  lightboxTitleEl.textContent = current.filename || current.photoId;
  lightboxImageEl.removeAttribute("src");
  lightboxEl.classList.add("active");
  lightboxEl.setAttribute("aria-hidden", "false");
  state.lightbox = { photos, index: safeIndex };
  updateLightboxControls();
  const objectUrl = await fetchBlobObjectUrl(current.originalSrc, state.originalObjectUrls, current.photoId);
  lightboxImageEl.src = objectUrl;
}

function updateLightboxControls() {
  if (!state.lightbox) return;
  const total = state.lightbox.photos.length;
  const idx = state.lightbox.index;
  lightboxCounterEl.textContent = `${idx + 1} / ${total}`;
  lightboxPrevBtnEl.disabled = idx <= 0;
  lightboxNextBtnEl.disabled = idx >= total - 1;
}

async function shiftLightbox(step) {
  if (!state.lightbox) return;
  const nextIndex = state.lightbox.index + step;
  await openLightboxAt(state.lightbox.photos, nextIndex);
}

async function downloadLightboxOriginal() {
  if (!state.lightbox) return;
  const current = state.lightbox.photos[state.lightbox.index];
  const { photoId, originalSrc, filename } = current;
  const objectUrl = await fetchBlobObjectUrl(originalSrc, state.originalObjectUrls, photoId);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename || `${photoId}.jpg`;
  link.click();
}

function resetFilters() {
  searchInputEl.value = "";
  photographerFilterEl.value = "";
  dateFromEl.value = "";
  dateToEl.value = "";
  state.lastRenderSignature = "";
  fetchBatchesAndRender().catch((e) => setStatus(String(e), true));
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
  clearSessionState();
  for (const objectUrl of state.imageObjectUrls.values()) {
    URL.revokeObjectURL(objectUrl);
  }
  for (const objectUrl of state.originalObjectUrls.values()) {
    URL.revokeObjectURL(objectUrl);
  }
  state.imageObjectUrls.clear();
  state.originalObjectUrls.clear();
  state.lastRenderSignature = "";
  closeLightbox();
  stopPolling();
  notificationsEl.innerHTML = "";
  batchesEl.innerHTML = "";
  autoYandexToggleEl.checked = false;
  searchInputEl.value = "";
  photographerFilterEl.innerHTML = '<option value="">Все фотографы</option>';
  dateFromEl.value = "";
  dateToEl.value = "";
  batchStatsEl.innerHTML = "";
  metaEl.textContent = "";
  setStatus("Выход выполнен");
}

function startPolling() {
  stopPolling();
  state.pollTimer = setInterval(async () => {
    try {
      await fetchNotifications();
      if (state.activeTab === "packages" && !document.hidden) {
        await fetchBatchesAndRender();
      }
    } catch (err) {
      setStatus(`Ошибка polling: ${String(err)}`, true);
    }
  }, 15000);
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
  await fetchBatchesAndRender();
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

function setButtonTempState(action, batchId, label) {
  const selector = `button[data-action="${action}"][data-batch-id="${batchId}"]`;
  const button = batchesEl.querySelector(selector);
  if (!button) return;
  const original = button.textContent;
  button.textContent = label;
  button.disabled = true;
  setTimeout(() => {
    button.textContent = original.includes("...") ? original.replace("...", "") : original;
    button.disabled = false;
  }, 1200);
}

function downloadBatch(batchId) {
  if (!state.token) throw new Error("Сначала выполните вход");
  withActionState("download", batchId, true);
  fetchBatchesAndRender().catch(() => {});
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
      setButtonTempState("download", batchId, "Готово");
      setStatus(`Пакет скачан и убран из активного списка: ${filename}`);
    })
    .catch((err) => setStatus(`Ошибка скачивания: ${String(err)}`, true))
    .finally(() => {
      withActionState("download", batchId, false);
      fetchBatchesAndRender().catch(() => {});
    });
}

async function uploadBatchToYandex(batchId) {
  if (!state.token) throw new Error("Сначала выполните вход");
  withActionState("yadisk", batchId, true);
  await fetchBatchesAndRender();
  try {
    const result = await apiJson(`/api/batches/${batchId}/upload-yandex`, {
      method: "POST",
    });
    setStatus(`На Я.Диск выгружено файлов: ${result.uploaded_files}, папка: ${result.remote_path}`);
    setButtonTempState("yadisk", batchId, "Готово");
  } finally {
    withActionState("yadisk", batchId, false);
    await fetchBatchesAndRender();
  }
}

document.getElementById("loginBtn").addEventListener("click", () => login().catch((e) => setStatus(String(e), true)));
document.getElementById("logoutBtn").addEventListener("click", logout);
document.getElementById("refreshBtn").addEventListener("click", () => {
  Promise.all([fetchNotifications(), fetchBatchesAndRender()]).catch((e) => setStatus(String(e), true));
});
document.getElementById("enablePushBtn").addEventListener("click", () => enablePush().catch((e) => setStatus(String(e), true)));
document.getElementById("disablePushBtn").addEventListener("click", () => disablePush().catch((e) => setStatus(String(e), true)));
document.getElementById("testPushBtn").addEventListener("click", () => sendTestPush().catch((e) => setStatus(String(e), true)));
document.getElementById("realBatchBtn").addEventListener("click", () => triggerRealBatch().catch((e) => setStatus(String(e), true)));
document.getElementById("markReadBtn").addEventListener("click", () => markRead().catch((e) => setStatus(String(e), true)));
document.getElementById("resetFiltersBtn").addEventListener("click", resetFilters);
refreshPackagesBtnEl.addEventListener("click", () => fetchBatchesAndRender().catch((e) => setStatus(String(e), true)));
cleanupProcessedBtnEl.addEventListener("click", () => cleanupProcessedBatches().catch((e) => setStatus(String(e), true)));
searchInputEl.addEventListener("input", () => fetchBatchesAndRender().catch((e) => setStatus(String(e), true)));
photographerFilterEl.addEventListener("change", () => fetchBatchesAndRender().catch((e) => setStatus(String(e), true)));
dateFromEl.addEventListener("change", () => fetchBatchesAndRender().catch((e) => setStatus(String(e), true)));
dateToEl.addEventListener("change", () => fetchBatchesAndRender().catch((e) => setStatus(String(e), true)));
for (const btn of tabButtons) {
  btn.addEventListener("click", () => setActiveTab(btn.getAttribute("data-tab-target")));
}
lightboxCloseBtnEl.addEventListener("click", closeLightbox);
lightboxPrevBtnEl.addEventListener("click", () => shiftLightbox(-1).catch((e) => setStatus(String(e), true)));
lightboxNextBtnEl.addEventListener("click", () => shiftLightbox(1).catch((e) => setStatus(String(e), true)));
lightboxDownloadBtnEl.addEventListener("click", () => downloadLightboxOriginal().catch((e) => setStatus(String(e), true)));
lightboxEl.addEventListener("click", (event) => {
  if (event.target === lightboxEl) closeLightbox();
});
window.addEventListener("keydown", (event) => {
  if (!state.lightbox) return;
  if (event.key === "Escape") {
    closeLightbox();
    return;
  }
  if (event.key === "ArrowLeft") {
    shiftLightbox(-1).catch((e) => setStatus(String(e), true));
    return;
  }
  if (event.key === "ArrowRight") {
    shiftLightbox(1).catch((e) => setStatus(String(e), true));
  }
});
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
    return;
  }
  if (action === "open-image") {
    const batchId = target.getAttribute("data-batch-id");
    const photoIndexRaw = target.getAttribute("data-photo-index");
    const photoIndex = Number(photoIndexRaw || "0");
    if (batchId && state.batchCache.has(batchId)) {
      const detail = state.batchCache.get(batchId);
      const photos = detail.photos.map((photo) => ({
        photoId: photo.id,
        originalSrc: photo.image_url,
        filename: photo.filename,
      }));
      openLightboxAt(photos, Number.isFinite(photoIndex) ? photoIndex : 0).catch((e) => setStatus(String(e), true));
      return;
    }
    const photoId = target.getAttribute("data-photo-id");
    const originalSrc = target.getAttribute("data-original-src");
    const filename = target.getAttribute("data-filename") || "";
    openLightbox(photoId, originalSrc, filename).catch((e) => setStatus(String(e), true));
  }
});

if (state.token) {
  Promise.all([fetchNotifications(), loadAutoYandexMode(), fetchBatchesAndRender()])
    .then(startPolling)
    .then(() => setStatus("Сессия восстановлена, polling активен"))
    .catch((e) => {
      if (!String(e).startsWith("401:")) {
        setStatus(`Нужен вход: ${String(e)}`, true);
      }
    });
}

setActiveTab("packages");
