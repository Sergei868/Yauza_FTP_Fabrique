const state = {
  token: localStorage.getItem("pf_token") || "",
  pollTimer: null,
  batchCache: new Map(),
  allBatches: [],
  actionsInProgress: new Set(),
  imageObjectUrls: new Map(),
  originalObjectUrls: new Map(),
  activeTab: "packages",
  lastRenderSignature: "",
  lightbox: null,
  archiveTtlOptions: [],
  userRole: "bild",
  archiveBatchCache: new Map(),
  archiveModal: null,
  adminSecretsHideTimer: null,
};

const statusEl = document.getElementById("status");
const metaEl = document.getElementById("meta");
const notificationsEl = document.getElementById("notifications");
const batchesEl = document.getElementById("batches");
const batchStatsEl = document.getElementById("batchStats");
const archiveUsageEl = document.getElementById("archiveUsage");
const archiveBatchesEl = document.getElementById("archiveBatches");
const autoYandexToggleEl = document.getElementById("autoYandexToggle");
const archiveTtlInputEl = document.getElementById("archiveTtlInput");
const archiveLimitInputEl = document.getElementById("archiveLimitInput");
const archiveTtlUpBtnEl = document.getElementById("archiveTtlUpBtn");
const archiveTtlDownBtnEl = document.getElementById("archiveTtlDownBtn");
const archiveLimitUpBtnEl = document.getElementById("archiveLimitUpBtn");
const archiveLimitDownBtnEl = document.getElementById("archiveLimitDownBtn");
const adminPanelEl = document.getElementById("adminPanel");
const adminBildUsernameEl = document.getElementById("adminBildUsername");
const adminBildPasswordEl = document.getElementById("adminBildPassword");
const adminAdminUsernameEl = document.getElementById("adminAdminUsername");
const adminAdminPasswordEl = document.getElementById("adminAdminPassword");
const adminFtpBildUsernameEl = document.getElementById("adminFtpBildUsername");
const adminFtpBildPasswordEl = document.getElementById("adminFtpBildPassword");
const adminFtpPhotographerUsernameEl = document.getElementById("adminFtpPhotographerUsername");
const adminFtpPhotographerPasswordEl = document.getElementById("adminFtpPhotographerPassword");
const adminYandexTokenEl = document.getElementById("adminYandexToken");
const adminYandexRemotePathEl = document.getElementById("adminYandexRemotePath");
const adminRevealConfirmPasswordEl = document.getElementById("adminRevealConfirmPassword");
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
const archiveModalEl = document.getElementById("archiveModal");
const archiveModalTitleEl = document.getElementById("archiveModalTitle");
const archiveModalGridEl = document.getElementById("archiveModalGrid");
const archiveModalDownloadBtnEl = document.getElementById("archiveModalDownloadBtn");
const archiveModalDownloadSelectedBtnEl = document.getElementById("archiveModalDownloadSelectedBtn");
const archiveModalCloseBtnEl = document.getElementById("archiveModalCloseBtn");

function setStatus(text, isError = false) {
  if (!statusEl) return;
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
  if (!state.token) return;
  if (tabId === "archive") {
    fetchArchiveData().catch((e) => setStatus(String(e), true));
    return;
  }
  if (tabId === "packages") {
    fetchBatchesAndRender().catch((e) => setStatus(String(e), true));
  }
}

function getLightboxRefs() {
  return {
    root: document.getElementById("lightbox"),
    image: document.getElementById("lightboxImage"),
    title: document.getElementById("lightboxTitle"),
    counter: document.getElementById("lightboxCounter"),
    prevBtn: document.getElementById("lightboxPrevBtn"),
    nextBtn: document.getElementById("lightboxNextBtn"),
  };
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
  metaEl.textContent = "";
  notificationsEl.innerHTML = "";
  for (const item of items) {
    const dateSource = item.captured_at || item.created_at;
    const dt = new Date(dateSource);
    const parts = new Intl.DateTimeFormat("ru-RU", {
      day: "numeric",
      month: "long",
      hour: "2-digit",
      minute: "2-digit",
    }).formatToParts(dt);
    const day = parts.find((part) => part.type === "day")?.value || "";
    const month = parts.find((part) => part.type === "month")?.value || "";
    const hour = parts.find((part) => part.type === "hour")?.value || "";
    const minute = parts.find((part) => part.type === "minute")?.value || "";
    const dateLabel = `${day} ${month} ${hour}:${minute}`.trim();
    const photographer = item.photographer || "unknown";
    const fileCount = Number(item.file_count || 0);
    const dailySequence = Number(item.daily_sequence || 0);
    const totalBytes = Number(item.total_size_bytes || 0);
    const totalMbRounded = Math.round(totalBytes / (1024 * 1024));
    const mbLabel = `${new Intl.NumberFormat("ru-RU").format(totalMbRounded)} МБ`;
    const div = document.createElement("div");
    div.className = "notif";
    div.innerHTML = `
      <div>${esc(`${photographer}: ${dateLabel} #${dailySequence || "-"}`)}</div>
      <div class="mono">${esc(`${fileCount} фото, ${mbLabel}`)}</div>
    `;
    notificationsEl.appendChild(div);
  }
}

async function fetchNotifications() {
  const items = await apiJson("/api/notifications?limit=20");
  renderNotifications(items);
}

async function clearNotifications() {
  if (!state.token) throw new Error("Сначала выполните вход");
  const result = await apiJson("/api/notifications/clear", {
    method: "POST",
  });
  setStatus(`Очищено уведомлений: ${result.deleted}`);
  await fetchNotifications();
}

function formatRuDateTime(isoString) {
  const dt = new Date(isoString);
  const parts = new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  }).formatToParts(dt);
  const day = parts.find((part) => part.type === "day")?.value || "";
  const month = parts.find((part) => part.type === "month")?.value || "";
  const hour = parts.find((part) => part.type === "hour")?.value || "";
  const minute = parts.find((part) => part.type === "minute")?.value || "";
  return `${day} ${month} ${hour}:${minute}`.trim();
}

function renderArchiveUsage(usage) {
  if (!archiveUsageEl) return;
  const used = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(usage.used_gb || 0));
  const limit = new Intl.NumberFormat("ru-RU").format(Number(usage.limit_gb || 0));
  const percent = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(Number(usage.usage_percent || 0));
  archiveUsageEl.textContent = `Архив: ${used} / ${limit} ГБ (${percent}%)`;
}

function renderArchiveBatches(batches) {
  if (!archiveBatchesEl) return;
  if (!batches.length) {
    archiveBatchesEl.innerHTML = '<div class="muted">Архив пока пуст.</div>';
    return;
  }
  archiveBatchesEl.innerHTML = batches.map((batch) => {
    const removedLabel = formatRuDateTime(batch.removed_from_incoming_at);
    const expiresLabel = formatRuDateTime(batch.archive_expires_at);
    const meta = formatBatchMeta(batch);
    return `
      <div class="batch-card">
        <div class="batch-top">
          <div>
            <div class="batch-title">${esc(batch.photographer)}</div>
            <div class="batch-sub">${esc(meta.line1)}<br>${esc(`${meta.line2} | Удален из incoming: ${removedLabel} | лежит до ${expiresLabel}`)}</div>
          </div>
        </div>
        <div class="archive-preview-row" data-archive-preview-row="${esc(batch.id)}">
          <span class="muted">Загрузка превью...</span>
        </div>
        <div class="row">
          <button data-action="view-archive-all" data-batch-id="${esc(batch.id)}">Просмотреть все</button>
          <button data-action="download-archive" data-batch-id="${esc(batch.id)}">Скачать весь пакет</button>
        </div>
      </div>
    `;
  }).join("");
}

async function fetchArchiveBatchDetail(batchId) {
  if (state.archiveBatchCache.has(batchId)) return state.archiveBatchCache.get(batchId);
  const detail = await apiJson(`/api/archive/batches/${batchId}`);
  state.archiveBatchCache.set(batchId, detail);
  return detail;
}

async function hydrateArchivePreviews(batches) {
  if (!archiveBatchesEl) return;
  for (const batch of batches) {
    const row = archiveBatchesEl.querySelector(`[data-archive-preview-row="${batch.id}"]`);
    if (!(row instanceof HTMLElement)) continue;
    try {
      const detail = await fetchArchiveBatchDetail(batch.id);
      const firstPhotos = (detail.photos || []).slice(0, 8);
      if (!firstPhotos.length) {
        row.innerHTML = '<span class="muted">Нет файлов для превью.</span>';
        continue;
      }
      row.innerHTML = firstPhotos.map((photo) => (
        `<img class="archive-preview-item" data-archive-preview-photo="${esc(photo.id)}" alt="${esc(photo.filename)}" title="${esc(photo.filename)}" />`
      )).join("");
      const imgTargets = [...row.querySelectorAll("img[data-archive-preview-photo]")];
      for (const imgEl of imgTargets) {
        const photoId = imgEl.getAttribute("data-archive-preview-photo") || "";
        const photo = firstPhotos.find((item) => item.id === photoId);
        if (!photo) continue;
        try {
          const objectUrl = await fetchBlobObjectUrl(photo.thumbnail_url || photo.image_url, state.imageObjectUrls, photo.id);
          imgEl.src = objectUrl;
        } catch (_err) {
          imgEl.alt = `${imgEl.alt || "preview"} (ошибка)`;
        }
      }
    } catch (_err) {
      row.innerHTML = '<span class="muted">Не удалось загрузить превью.</span>';
    }
  }
}

async function fetchArchiveData() {
  if (!state.token) return;
  const [usage, batches] = await Promise.all([
    apiJson("/api/archive/usage"),
    apiJson("/api/archive/batches?limit=50"),
  ]);
  const knownIds = new Set(batches.map((item) => item.id));
  for (const cachedId of state.archiveBatchCache.keys()) {
    if (!knownIds.has(cachedId)) state.archiveBatchCache.delete(cachedId);
  }
  renderArchiveUsage(usage);
  renderArchiveBatches(batches);
  await hydrateArchivePreviews(batches);
}

async function loadArchiveSettings() {
  if (!state.token) return;
  const settings = await apiJson("/api/archive/settings");
  state.archiveTtlOptions = (settings.ttl_options_hours || [])
    .map((item) => Number(item))
    .filter((item) => Number.isFinite(item) && item > 0)
    .sort((a, b) => a - b);
  if (archiveTtlInputEl) {
    archiveTtlInputEl.value = String(settings.ttl_hours);
  }
  if (archiveLimitInputEl) {
    archiveLimitInputEl.value = String(settings.limit_gb);
  }
}

function applyRoleUi() {
  if (!adminPanelEl) return;
  const isAdmin = state.userRole === "admin";
  adminPanelEl.classList.toggle("visible", isAdmin);
}

function clearAdminSecretFields() {
  if (adminBildPasswordEl) adminBildPasswordEl.value = "";
  if (adminAdminPasswordEl) adminAdminPasswordEl.value = "";
  if (adminFtpBildPasswordEl) adminFtpBildPasswordEl.value = "";
  if (adminFtpPhotographerPasswordEl) adminFtpPhotographerPasswordEl.value = "";
  if (adminYandexTokenEl) adminYandexTokenEl.value = "";
}

function scheduleAdminSecretsAutoHide(seconds) {
  if (state.adminSecretsHideTimer) {
    clearTimeout(state.adminSecretsHideTimer);
    state.adminSecretsHideTimer = null;
  }
  const ttlMs = Math.max(1, Number(seconds || 60)) * 1000;
  state.adminSecretsHideTimer = setTimeout(() => {
    clearAdminSecretFields();
    state.adminSecretsHideTimer = null;
    setStatus("Секреты снова скрыты");
  }, ttlMs);
}

async function fetchAuthMe() {
  if (!state.token) return;
  const me = await apiJson("/api/auth/me");
  state.userRole = me.role || "bild";
  applyRoleUi();
}

async function loadAdminSettings() {
  if (!state.token) throw new Error("Сначала выполните вход");
  if (state.userRole !== "admin") throw new Error("Требуется вход под админом");
  const data = await apiJson("/api/admin/settings");
  if (adminBildUsernameEl) adminBildUsernameEl.value = data.bild_username || "";
  if (adminBildPasswordEl) adminBildPasswordEl.value = data.bild_password || "";
  if (adminAdminUsernameEl) adminAdminUsernameEl.value = data.admin_username || "";
  if (adminAdminPasswordEl) adminAdminPasswordEl.value = data.admin_password || "";
  if (adminFtpBildUsernameEl) adminFtpBildUsernameEl.value = data.ftp_bild_username || "";
  if (adminFtpBildPasswordEl) adminFtpBildPasswordEl.value = data.ftp_bild_password || "";
  if (adminFtpPhotographerUsernameEl) adminFtpPhotographerUsernameEl.value = data.ftp_photographer_username || "";
  if (adminFtpPhotographerPasswordEl) {
    adminFtpPhotographerPasswordEl.value = data.ftp_photographer_password || "";
  }
  if (adminYandexRemotePathEl) adminYandexRemotePathEl.value = data.yandex_remote_base_path || "";
  clearAdminSecretFields();
  setStatus("Админ-настройки загружены (секреты скрыты в API)");
}

async function revealAdminSecretsTemporarily() {
  if (!state.token) throw new Error("Сначала выполните вход");
  if (state.userRole !== "admin") throw new Error("Требуется вход под админом");
  const confirmPassword = adminRevealConfirmPasswordEl?.value || "";
  if (!confirmPassword.trim()) throw new Error("Введите пароль подтверждения рядом с кнопкой показа секретов");
  const payload = await apiJson("/api/admin/settings/reveal-secrets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ admin_password: confirmPassword }),
  });
  if (adminBildPasswordEl) adminBildPasswordEl.value = payload.bild_password || "";
  if (adminAdminPasswordEl) adminAdminPasswordEl.value = payload.admin_password || "";
  if (adminFtpBildPasswordEl) adminFtpBildPasswordEl.value = payload.ftp_bild_password || "";
  if (adminFtpPhotographerPasswordEl) adminFtpPhotographerPasswordEl.value = payload.ftp_photographer_password || "";
  if (adminYandexTokenEl) adminYandexTokenEl.value = payload.yandex_oauth_token || "";
  if (adminRevealConfirmPasswordEl) adminRevealConfirmPasswordEl.value = "";
  scheduleAdminSecretsAutoHide(payload.expires_in_seconds || 60);
  setStatus(`Секреты показаны на ${payload.expires_in_seconds || 60} сек`);
}

async function saveAdminSettings() {
  if (!state.token) throw new Error("Сначала выполните вход");
  if (state.userRole !== "admin") throw new Error("Требуется вход под админом");
  const payload = {
    bild_username: adminBildUsernameEl?.value?.trim() || undefined,
    bild_password: adminBildPasswordEl?.value || undefined,
    admin_username: adminAdminUsernameEl?.value?.trim() || undefined,
    admin_password: adminAdminPasswordEl?.value || undefined,
    ftp_bild_username: adminFtpBildUsernameEl?.value?.trim() || undefined,
    ftp_bild_password: adminFtpBildPasswordEl?.value || undefined,
    ftp_photographer_username: adminFtpPhotographerUsernameEl?.value?.trim() || undefined,
    ftp_photographer_password: adminFtpPhotographerPasswordEl?.value || undefined,
    yandex_oauth_token: adminYandexTokenEl?.value?.trim() || undefined,
    yandex_remote_base_path: adminYandexRemotePathEl?.value?.trim() || undefined,
  };
  const sanitizedPayload = Object.fromEntries(
    Object.entries(payload).filter(([, value]) => value !== undefined && value !== ""),
  );
  if (!Object.keys(sanitizedPayload).length) {
    setStatus("Нет изменений для сохранения", true);
    return;
  }
  await apiJson("/api/admin/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(sanitizedPayload),
  });
  setStatus("Админ-настройки сохранены");
  await Promise.all([fetchAuthMe(), loadAdminSettings()]);
}

async function applyAdminFtpSettings() {
  if (!state.token) throw new Error("Сначала выполните вход");
  if (state.userRole !== "admin") throw new Error("Требуется вход под админом");
  const ok = window.confirm(
    "Применить FTP-настройки на сервере сейчас? Будут обновлены пользователи и перезапущен vsftpd.",
  );
  if (!ok) return;
  const result = await apiJson("/api/admin/apply-ftp", {
    method: "POST",
  });
  setStatus(`FTP применен: фотограф=${result.ftp_photographer_username}, бильд=${result.ftp_bild_username}`);
}

function getNearestTtlOption(value) {
  const options = state.archiveTtlOptions || [];
  if (!options.length) return value;
  let nearest = options[0];
  let minDistance = Math.abs(options[0] - value);
  for (const option of options) {
    const distance = Math.abs(option - value);
    if (distance < minDistance) {
      nearest = option;
      minDistance = distance;
    }
  }
  return nearest;
}

function stepTtlValue(direction) {
  if (!archiveTtlInputEl) return;
  const options = state.archiveTtlOptions || [];
  if (!options.length) {
    const raw = Number(archiveTtlInputEl.value || "1");
    const next = Math.max(1, raw + direction);
    archiveTtlInputEl.value = String(next);
    return;
  }
  const current = Number(archiveTtlInputEl.value || options[0]);
  const normalized = getNearestTtlOption(current);
  const currentIndex = options.findIndex((item) => item === normalized);
  const nextIndex = Math.max(0, Math.min(options.length - 1, currentIndex + direction));
  archiveTtlInputEl.value = String(options[nextIndex]);
}

async function saveArchiveSettings() {
  if (!state.token) throw new Error("Сначала выполните вход");
  const ttlHours = getNearestTtlOption(Number(archiveTtlInputEl?.value || "0"));
  const limitGb = Number(archiveLimitInputEl?.value || "0");
  const settings = await apiJson("/api/archive/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ttl_hours: ttlHours, limit_gb: limitGb }),
  });
  if (archiveTtlInputEl) archiveTtlInputEl.value = String(settings.ttl_hours);
  if (archiveLimitInputEl) archiveLimitInputEl.value = String(settings.limit_gb);
  setStatus("Настройки архива сохранены");
  await fetchArchiveData();
}

async function clearArchive() {
  if (!state.token) throw new Error("Сначала выполните вход");
  const ok = window.confirm("Очистить архив originals полностью?");
  if (!ok) return;
  const result = await apiJson("/api/archive/clear", { method: "POST" });
  setStatus(`Архив очищен: пакетов ${result.cleared_batches}, файлов ${result.deleted_files}`);
  await fetchArchiveData();
}

function esc(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function formatBatchMeta(batch) {
  const captured = new Date(batch.captured_at);
  const dateParts = new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  }).formatToParts(captured);
  const day = dateParts.find((part) => part.type === "day")?.value || "";
  const month = dateParts.find((part) => part.type === "month")?.value || "";
  const hour = dateParts.find((part) => part.type === "hour")?.value || "";
  const minute = dateParts.find((part) => part.type === "minute")?.value || "";
  const dateLabel = `${day} ${month} ${hour}:${minute}`.trim();
  const totalBytes = Number(batch.total_size_bytes || 0);
  const totalMbRounded = Math.round(totalBytes / (1024 * 1024));
  const mbLabel = `${new Intl.NumberFormat("ru-RU").format(totalMbRounded)} МБ`;
  return {
    line1: `${dateLabel} | ${batch.file_count} фото`,
    line2: `${batch.broken_files_count} битых | ${mbLabel} | #${batch.daily_sequence}`,
  };
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
      (photo, index) => `<div class="thumb-item">
        <label class="thumb-select" title="Выбрать фото">
          <input type="checkbox"
            data-photo-checkbox="1"
            data-batch-id="${esc(batch.id)}"
            data-photo-id="${esc(photo.id)}" />
        </label>
        <button class="thumb-btn" type="button"
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
        /></button>
      </div>`,
    )
    .join("");
  const downloadAllBusy = isActionRunning("download-all", batch.id);
  const downloadSelectedBusy = isActionRunning("download-selected", batch.id);
  const meta = formatBatchMeta(batch);
  return `
    <div class="batch-card" id="batch-${batch.id}">
      <div class="batch-top">
        <div>
          <div class="batch-title">${esc(batch.photographer)}</div>
          <div class="batch-sub">${esc(meta.line1)}<br>${esc(meta.line2)}</div>
        </div>
      </div>
      <div class="row">
        <button data-action="download-all" data-batch-id="${batch.id}" ${downloadAllBusy ? "disabled" : ""}>${downloadAllBusy ? "Скачивание..." : "Скачать все"}</button>
        <button data-action="download-selected" data-batch-id="${batch.id}" ${downloadSelectedBusy ? "disabled" : ""}>${downloadSelectedBusy ? "Скачивание..." : "Скачать выбранное"}</button>
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
  const batches = await apiJson("/api/batches?limit=50&include_photos=true");
  state.allBatches = batches;
  renderBatchStats(batches, batches);
  const renderSignature = JSON.stringify({
    ids: batches.map((item) => item.id),
    status: batches.map((item) => item.status),
    files: batches.map((item) => item.file_count),
    broken: batches.map((item) => item.broken_files_count),
  });
  if (!batches.length) {
    batchesEl.innerHTML = '<div class="muted">Пока нет пакетов.</div>';
    state.lastRenderSignature = renderSignature;
    return;
  }
  if (renderSignature === state.lastRenderSignature) {
    return;
  }
  const knownIds = new Set(batches.map((batch) => batch.id));
  for (const cachedId of state.batchCache.keys()) {
    if (!knownIds.has(cachedId)) state.batchCache.delete(cachedId);
  }
  const rendered = [];
  for (const batch of batches) {
    const photos = Array.isArray(batch.photos) ? batch.photos : [];
    const detail = { photos };
    state.batchCache.set(batch.id, detail);
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

function renderBatchStats(allBatches, filteredBatches) {
  const totalBroken = filteredBatches.reduce((acc, item) => acc + item.broken_files_count, 0);
  const chips = [
    `Пакеты: ${allBatches.length}`,
    `Показано: ${filteredBatches.length}`,
    `Битых: ${totalBroken}`,
  ];
  batchStatsEl.innerHTML = chips.map((item) => `<span class="chip">${esc(item)}</span>`).join("");
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
  const refs = getLightboxRefs();
  if (!refs.root || !refs.image || !refs.title) return;
  refs.title.textContent = filename || photoId;
  refs.image.removeAttribute("src");
  refs.image.alt = filename || "Оригинал";
  refs.root.classList.add("active");
  refs.root.setAttribute("aria-hidden", "false");
  const objectUrl = await fetchBlobObjectUrl(originalSrc, state.originalObjectUrls, photoId);
  refs.image.src = objectUrl;
  state.lightbox = {
    photos: [{ photoId, originalSrc, filename }],
    index: 0,
  };
  updateLightboxControls();
}

function closeLightbox() {
  const refs = getLightboxRefs();
  if (!refs.root || !refs.image) return;
  refs.root.classList.remove("active");
  refs.root.setAttribute("aria-hidden", "true");
  refs.image.removeAttribute("src");
  state.lightbox = null;
}

async function openLightboxAt(photos, index) {
  if (!photos.length) return;
  const refs = getLightboxRefs();
  if (!refs.root || !refs.image || !refs.title) return;
  const safeIndex = Math.max(0, Math.min(index, photos.length - 1));
  const current = photos[safeIndex];
  refs.title.textContent = current.filename || current.photoId;
  refs.image.removeAttribute("src");
  refs.root.classList.add("active");
  refs.root.setAttribute("aria-hidden", "false");
  state.lightbox = { photos, index: safeIndex };
  updateLightboxControls();
  const objectUrl = await fetchBlobObjectUrl(current.originalSrc, state.originalObjectUrls, current.photoId);
  refs.image.src = objectUrl;
}

function updateLightboxControls() {
  const refs = getLightboxRefs();
  if (!state.lightbox || !refs.counter || !refs.prevBtn || !refs.nextBtn) return;
  const total = state.lightbox.photos.length;
  const idx = state.lightbox.index;
  refs.counter.textContent = `${idx + 1} / ${total}`;
  refs.prevBtn.disabled = idx <= 0;
  refs.nextBtn.disabled = idx >= total - 1;
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

function getSelectedPhotoIds(batchId) {
  return [...batchesEl.querySelectorAll(`input[data-photo-checkbox="1"][data-batch-id="${batchId}"]:checked`)]
    .map((el) => el.getAttribute("data-photo-id"))
    .filter((item) => !!item);
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
  state.userRole = tokenBody.role || "bild";
  localStorage.setItem("pf_token", state.token);
  applyRoleUi();
  setStatus(`JWT получен, TTL ${tokenBody.expires_in_seconds}s`);
  await fetchAuthMe();
  await fetchNotifications();
  if (state.userRole === "admin") {
    await loadAutoYandexMode();
  } else if (autoYandexToggleEl) {
    autoYandexToggleEl.checked = false;
  }
  await loadArchiveSettings();
  await fetchBatchesAndRender();
  await fetchArchiveData();
  if (state.userRole === "admin") {
    await loadAdminSettings();
  }
  startPolling();
}

function logout() {
  clearSessionState();
  if (state.adminSecretsHideTimer) {
    clearTimeout(state.adminSecretsHideTimer);
    state.adminSecretsHideTimer = null;
  }
  clearAdminSecretFields();
  for (const objectUrl of state.imageObjectUrls.values()) {
    URL.revokeObjectURL(objectUrl);
  }
  for (const objectUrl of state.originalObjectUrls.values()) {
    URL.revokeObjectURL(objectUrl);
  }
  state.imageObjectUrls.clear();
  state.originalObjectUrls.clear();
  state.lastRenderSignature = "";
  state.userRole = "bild";
  applyRoleUi();
  closeLightbox();
  stopPolling();
  notificationsEl.innerHTML = "";
  batchesEl.innerHTML = "";
  autoYandexToggleEl.checked = false;
  batchStatsEl.innerHTML = "";
  if (archiveUsageEl) archiveUsageEl.textContent = "Архив: -";
  if (archiveBatchesEl) archiveBatchesEl.innerHTML = "";
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
      } else if (state.activeTab === "archive" && !document.hidden) {
        await fetchArchiveData();
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

  const reg = await navigator.serviceWorker.register("/sw.js?v=20260524-1649");
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
    body: JSON.stringify({ title: "Bildboard Yauza", body: "ТестФотограф 5 файлов 12 МБ 1 битых" }),
  });
  setStatus(`Test push: sent=${result.sent}, failed=${result.failed}`);
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
  if (!state.token || state.userRole !== "admin") return;
  const mode = await apiJson("/api/yandex/auto-upload");
  autoYandexToggleEl.checked = !!mode.enabled;
}

async function updateAutoYandexMode(enabled) {
  if (!state.token) throw new Error("Сначала выполните вход");
  if (state.userRole !== "admin") throw new Error("Только админ может менять авто-загрузку Я.Диска");
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
  withActionState("download-all", batchId, true);
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
      setButtonTempState("download-all", batchId, "Готово");
      setStatus(`Скачаны все фото пакета: ${filename}`);
    })
    .catch((err) => setStatus(`Ошибка скачивания: ${String(err)}`, true))
    .finally(() => {
      withActionState("download-all", batchId, false);
      fetchBatchesAndRender().catch(() => {});
      fetchArchiveData().catch(() => {});
    });
}

function downloadSelectedBatch(batchId) {
  if (!state.token) throw new Error("Сначала выполните вход");
  const selectedPhotoIds = getSelectedPhotoIds(batchId);
  if (!selectedPhotoIds.length) {
    setStatus("Выберите хотя бы одну фотографию для скачивания", true);
    return;
  }
  withActionState("download-selected", batchId, true);
  fetchBatchesAndRender().catch(() => {});
  fetch(`/api/batches/${batchId}/download-selected`, {
    method: "POST",
    headers: getHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ photo_ids: selectedPhotoIds }),
  })
    .then(async (response) => {
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `download failed ${response.status}`);
      }
      const blob = await response.blob();
      const contentDisposition = response.headers.get("Content-Disposition") || "";
      const match = /filename="([^"]+)"/.exec(contentDisposition);
      const filename = match ? match[1] : `batch-${batchId}-selected.zip`;
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(objectUrl);
      setButtonTempState("download-selected", batchId, "Готово");
      setStatus(`Скачаны выбранные фото: ${filename}`);
    })
    .catch((err) => setStatus(`Ошибка скачивания выбранного: ${String(err)}`, true))
    .finally(() => {
      withActionState("download-selected", batchId, false);
      fetchBatchesAndRender().catch(() => {});
      fetchArchiveData().catch(() => {});
    });
}

function downloadArchiveBatch(batchId) {
  if (!state.token) throw new Error("Сначала выполните вход");
  fetch(`/api/archive/batches/${batchId}/download`, { headers: getHeaders() })
    .then(async (response) => {
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `archive download failed ${response.status}`);
      }
      const blob = await response.blob();
      const contentDisposition = response.headers.get("Content-Disposition") || "";
      const match = /filename="([^"]+)"/.exec(contentDisposition);
      const filename = match ? match[1] : `archive-${batchId}.zip`;
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(objectUrl);
      setStatus(`Скачан архивный пакет: ${filename}`);
    })
    .catch((err) => setStatus(`Ошибка скачивания архива: ${String(err)}`, true));
}

function downloadSelectedArchiveBatch(batchId, selectedPhotoIds) {
  if (!state.token) throw new Error("Сначала выполните вход");
  if (!selectedPhotoIds.length) {
    setStatus("Выберите хотя бы одно фото в архиве", true);
    return;
  }
  fetch(`/api/archive/batches/${batchId}/download-selected`, {
    method: "POST",
    headers: getHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ photo_ids: selectedPhotoIds }),
  })
    .then(async (response) => {
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `archive selected download failed ${response.status}`);
      }
      const blob = await response.blob();
      const contentDisposition = response.headers.get("Content-Disposition") || "";
      const match = /filename="([^"]+)"/.exec(contentDisposition);
      const filename = match ? match[1] : `archive-selected-${batchId}.zip`;
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(objectUrl);
      setStatus(`Скачаны выбранные фото из архива: ${filename}`);
    })
    .catch((err) => setStatus(`Ошибка скачивания выбранного архива: ${String(err)}`, true));
}

function closeArchiveModal() {
  if (!archiveModalEl || !archiveModalGridEl) return;
  archiveModalEl.classList.remove("active");
  archiveModalEl.setAttribute("aria-hidden", "true");
  archiveModalGridEl.innerHTML = "";
  state.archiveModal = null;
}

async function openArchiveModal(batchId) {
  if (!archiveModalEl || !archiveModalGridEl || !archiveModalTitleEl) return;
  const detail = await fetchArchiveBatchDetail(batchId);
  const photos = detail.photos || [];
  archiveModalTitleEl.textContent = `${detail.photographer} | ${photos.length} фото`;
  if (!photos.length) {
    archiveModalGridEl.innerHTML = '<div class="muted">Нет файлов для просмотра.</div>';
  } else {
    archiveModalGridEl.innerHTML = photos.map((photo, index) => `
      <div class="archive-modal-item">
        <label class="archive-modal-check">
          <input type="checkbox" data-archive-select-photo-id="${esc(photo.id)}" />
        </label>
        <button class="archive-modal-thumb"
          type="button"
          data-action="archive-open-photo"
          data-archive-index="${index}"
          title="${esc(photo.filename)}">
          <img data-archive-modal-photo-id="${esc(photo.id)}" alt="${esc(photo.filename)}" />
        </button>
      </div>
    `).join("");
    const imgTargets = [...archiveModalGridEl.querySelectorAll("img[data-archive-modal-photo-id]")];
    for (const imgEl of imgTargets) {
      const photoId = imgEl.getAttribute("data-archive-modal-photo-id") || "";
      const photo = photos.find((item) => item.id === photoId);
      if (!photo) continue;
      try {
        const objectUrl = await fetchBlobObjectUrl(photo.thumbnail_url || photo.image_url, state.imageObjectUrls, photo.id);
        imgEl.src = objectUrl;
      } catch (_err) {
        imgEl.alt = `${imgEl.alt || "preview"} (ошибка)`;
      }
    }
  }
  state.archiveModal = {
    batchId,
    photos: photos.map((photo) => ({
      photoId: photo.id,
      originalSrc: photo.image_url,
      filename: photo.filename,
    })),
    selectedPhotoIds: new Set(),
  };
  archiveModalEl.classList.add("active");
  archiveModalEl.setAttribute("aria-hidden", "false");
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

function bindIfExists(element, eventName, handler) {
  if (!element) return;
  element.addEventListener(eventName, handler);
}

bindIfExists(document.getElementById("loginBtn"), "click", () => login().catch((e) => setStatus(String(e), true)));
bindIfExists(document.getElementById("logoutBtn"), "click", logout);
bindIfExists(document.getElementById("refreshBtn"), "click", () => {
  Promise.all([
    fetchNotifications(),
    fetchBatchesAndRender(),
    fetchArchiveData(),
    loadArchiveSettings(),
    fetchAuthMe(),
    state.userRole === "admin" ? loadAdminSettings() : Promise.resolve(),
  ])
    .catch((e) => setStatus(String(e), true));
});
bindIfExists(document.getElementById("enablePushBtn"), "click", () => enablePush().catch((e) => setStatus(String(e), true)));
bindIfExists(document.getElementById("disablePushBtn"), "click", () => disablePush().catch((e) => setStatus(String(e), true)));
bindIfExists(document.getElementById("testPushBtn"), "click", () => sendTestPush().catch((e) => setStatus(String(e), true)));
bindIfExists(document.getElementById("realBatchBtn"), "click", () => triggerRealBatch().catch((e) => setStatus(String(e), true)));
bindIfExists(document.getElementById("clearNotificationsBtn"), "click", () => clearNotifications().catch((e) => setStatus(String(e), true)));
bindIfExists(document.getElementById("saveArchiveSettingsBtn"), "click", () => saveArchiveSettings().catch((e) => setStatus(String(e), true)));
bindIfExists(document.getElementById("clearArchiveBtn"), "click", () => clearArchive().catch((e) => setStatus(String(e), true)));
bindIfExists(document.getElementById("adminLoadSettingsBtn"), "click", () => loadAdminSettings().catch((e) => setStatus(String(e), true)));
bindIfExists(document.getElementById("adminRevealSecretsBtn"), "click", () => revealAdminSecretsTemporarily().catch((e) => setStatus(String(e), true)));
bindIfExists(document.getElementById("adminSaveSettingsBtn"), "click", () => saveAdminSettings().catch((e) => setStatus(String(e), true)));
bindIfExists(document.getElementById("adminApplyFtpBtn"), "click", () => applyAdminFtpSettings().catch((e) => setStatus(String(e), true)));
for (const toggleBtn of document.querySelectorAll("[data-toggle-password]")) {
  bindIfExists(toggleBtn, "click", () => {
    const selector = toggleBtn.getAttribute("data-toggle-password");
    if (!selector) return;
    const input = document.querySelector(selector);
    if (!(input instanceof HTMLInputElement)) return;
    input.type = input.type === "password" ? "text" : "password";
  });
}
bindIfExists(archiveTtlUpBtnEl, "click", () => stepTtlValue(1));
bindIfExists(archiveTtlDownBtnEl, "click", () => stepTtlValue(-1));
bindIfExists(archiveLimitUpBtnEl, "click", () => {
  if (!archiveLimitInputEl) return;
  archiveLimitInputEl.stepUp();
});
bindIfExists(archiveLimitDownBtnEl, "click", () => {
  if (!archiveLimitInputEl) return;
  archiveLimitInputEl.stepDown();
  if (Number(archiveLimitInputEl.value || "0") < 1) {
    archiveLimitInputEl.value = "1";
  }
});
for (const btn of tabButtons) {
  btn.addEventListener("click", () => setActiveTab(btn.getAttribute("data-tab-target")));
}
bindIfExists(lightboxCloseBtnEl, "click", closeLightbox);
bindIfExists(lightboxPrevBtnEl, "click", () => shiftLightbox(-1).catch((e) => setStatus(String(e), true)));
bindIfExists(lightboxNextBtnEl, "click", () => shiftLightbox(1).catch((e) => setStatus(String(e), true)));
bindIfExists(lightboxDownloadBtnEl, "click", () => downloadLightboxOriginal().catch((e) => setStatus(String(e), true)));
bindIfExists(lightboxEl, "click", (event) => {
  if (event.target === lightboxEl) closeLightbox();
});
bindIfExists(archiveModalCloseBtnEl, "click", closeArchiveModal);
bindIfExists(archiveModalDownloadBtnEl, "click", () => {
  if (!state.archiveModal?.batchId) return;
  downloadArchiveBatch(state.archiveModal.batchId);
});
bindIfExists(archiveModalDownloadSelectedBtnEl, "click", () => {
  if (!state.archiveModal?.batchId) return;
  const selected = [...(state.archiveModal.selectedPhotoIds || [])];
  downloadSelectedArchiveBatch(state.archiveModal.batchId, selected);
});
bindIfExists(archiveModalEl, "click", (event) => {
  if (event.target === archiveModalEl) closeArchiveModal();
});
bindIfExists(archiveModalGridEl, "change", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) return;
  if (target.getAttribute("data-archive-select-photo-id") === null) return;
  const photoId = target.getAttribute("data-archive-select-photo-id") || "";
  if (!photoId) return;
  if (!state.archiveModal?.selectedPhotoIds) return;
  if (target.checked) state.archiveModal.selectedPhotoIds.add(photoId);
  else state.archiveModal.selectedPhotoIds.delete(photoId);
});
bindIfExists(archiveModalGridEl, "click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const actionEl = target.closest("[data-action]");
  if (!(actionEl instanceof HTMLElement)) return;
  const action = actionEl.getAttribute("data-action");
  if (action !== "archive-open-photo") return;
  const index = Number(actionEl.getAttribute("data-archive-index") || "0");
  const photos = state.archiveModal?.photos || [];
  openLightboxAt(photos, Number.isFinite(index) ? index : 0).catch((e) => setStatus(String(e), true));
});
window.addEventListener("keydown", (event) => {
  if (state.archiveModal && event.key === "Escape") {
    closeArchiveModal();
    return;
  }
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
bindIfExists(autoYandexToggleEl, "change", (event) => {
  const enabled = !!event.target.checked;
  updateAutoYandexMode(enabled).catch((e) => setStatus(String(e), true));
});
bindIfExists(batchesEl, "click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const actionEl = target.closest("[data-action]");
  if (!(actionEl instanceof HTMLElement)) return;
  const action = actionEl.getAttribute("data-action");
  const batchId = actionEl.getAttribute("data-batch-id");
  if (!action || !batchId) return;
  if (action === "download-all") {
    downloadBatch(batchId);
    return;
  }
  if (action === "download-selected") {
    downloadSelectedBatch(batchId);
    return;
  }
  if (action === "yadisk") {
    uploadBatchToYandex(batchId).catch((e) => setStatus(String(e), true));
    return;
  }
  if (action === "open-image") {
    const batchId = actionEl.getAttribute("data-batch-id");
    const photoIndexRaw = actionEl.getAttribute("data-photo-index");
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
    const photoId = actionEl.getAttribute("data-photo-id");
    const originalSrc = actionEl.getAttribute("data-original-src");
    const filename = actionEl.getAttribute("data-filename") || "";
    openLightbox(photoId, originalSrc, filename).catch((e) => setStatus(String(e), true));
  }
});
bindIfExists(archiveBatchesEl, "click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const actionEl = target.closest("[data-action]");
  if (!(actionEl instanceof HTMLElement)) return;
  const action = actionEl.getAttribute("data-action");
  const batchId = actionEl.getAttribute("data-batch-id");
  if (action === "download-archive" && batchId) {
    downloadArchiveBatch(batchId);
    return;
  }
  if (action === "view-archive-all" && batchId) {
    openArchiveModal(batchId).catch((e) => setStatus(String(e), true));
  }
});

if (state.token) {
  Promise.all([
    fetchAuthMe(),
    fetchNotifications(),
    fetchBatchesAndRender(),
    fetchArchiveData(),
    loadArchiveSettings(),
  ])
    .then(() => (state.userRole === "admin" ? loadAutoYandexMode() : Promise.resolve()))
    .then(() => (state.userRole === "admin" ? loadAdminSettings() : Promise.resolve()))
    .then(startPolling)
    .then(() => setStatus("Сессия восстановлена, polling активен"))
    .catch((e) => {
      if (!String(e).startsWith("401:")) {
        setStatus(`Нужен вход: ${String(e)}`, true);
      }
    });
}

setActiveTab("packages");
