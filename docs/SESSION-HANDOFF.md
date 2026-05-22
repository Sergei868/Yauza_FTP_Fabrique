# Session Handoff (подробный контекст)

## 1) Цель проекта (зачем это делаем)

Собрать устойчивый production-процесс для фотопотока:

1. Фотографы заливают JPEG по FTP в свои подпапки.
2. Система автоматически фиксирует пачки после тишины.
3. Бильд получает уведомление и работает с пачкой через веб-кабинет.
4. Параллельно хранится legacy-совместимое зеркало на Яндекс.Диске (структура как в incoming), чтобы не ломать старый рабочий процесс.

Это MVP, который уже пригоден для реальной ежедневной работы.

## 2) Текущий production-статус

- Ветка разработки: `cursor/init-photofactory-foundation`.
- Основной URL кабинета: `https://work.yauzamedia.ru/bild`.
- Ядро MVP работает end-to-end:
  - FTP приём (`vsftpd`, upload-only, chroot).
  - Watcher (`yauza-watcher`, systemd).
  - PostgreSQL + Alembic.
  - FastAPI (`yauza-api`) + JWT auth.
  - In-App уведомления + PWA push.
  - Яндекс.Диск зеркалирование файловой структуры.

## 3) Что уже реализовано по фазам

### Фаза 1-4 (инфраструктура, ingestion, API)

- Камера грузит в `incoming/<photographer>/`.
- Watcher по таймауту тишины фиксирует batch.
- Файлы уходят в `originals` и `backup`.
- В БД сохраняются photographers/batches/photos, включая `broken_files_count`.
- В кабинете доступны карточки пачек, галерея и действия.

### Фаза 5 (уведомления)

- In-App: готово и работает.
- PWA push: готово и проверено.
- Telegram: код есть, но заблокирован исходящий трафик с VPS на `api.telegram.org:443`.
- MAX: адаптер готов, но webhook не подключен в runtime.

### Фаза 6 (Яндекс.Диск)

- Ручная и автоматическая загрузка готовы.
- Схема зеркала: `/Yauza_FTP_Mirror/<photographer>/<filename>.jpg`.
- Текущая логика соответствует требованию "слепок incoming-структуры".

### Фаза 7 (UI/UX кабинета бильда)

- Сделано:
  - табы `Пакеты / Уведомления / Настройки` (по умолчанию `Пакеты`);
  - фильтры (поиск, фотограф, даты), кнопки `Обновить пакеты` и `Убрать старые`;
  - оптимизация превью через thumbnail endpoint + ограничение конкуренции загрузки;
  - снижение мерцаний через защиту от лишних re-render;
  - lightbox просмотра оригинала, стрелки, клавиатура (`←`, `→`, `Esc`);
  - скачивание одного фото из lightbox;
  - корректная обработка `401` (сброс сессии, переход в `Настройки`, понятный статус).
- В работе:
  - мини-юзабилити проверка с 2-3 бильдами и фиксация обратной связи;
  - zoom в lightbox (`+/-`, колесо, fit/100%, индикатор масштаба) как следующий UI-штрих.

## 4) Что считать "истиной" при возобновлении работы

1. `PROJECT.md` и `docs/` — источник решений и договорённостей.
2. `docs/ROADMAP.md` — фактический статус фаз.
3. `docs/modules/*.md` — техническая детализация по модулям.
4. `docs/deploy-notes.md` — хронология изменений и проверок на VPS.

## 5) Критичные runtime-файлы на VPS

- `/etc/yauza/config.yaml` — runtime-конфиг приложения.
- `/etc/yauza/.db-password` — пароль PostgreSQL.
- `/etc/yauza/.api-auth-password` — пароль API пользователя `bild`.
- `/etc/yauza/pwa_vapid_private.pem` — приватный VAPID-ключ.

## 6) Быстрый health-check (VPS)

```bash
sudo systemctl status yauza-watcher --no-pager -n 30
sudo systemctl status yauza-api --no-pager -n 30
```

```bash
API_PASS=$(sudo cat /etc/yauza/.api-auth-password)
TOKEN=$(curl -sS -X POST http://127.0.0.1:8000/api/auth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=bild' \
  --data-urlencode "password=${API_PASS}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -sS -H "Authorization: Bearer ${TOKEN}" "http://127.0.0.1:8000/api/batches?limit=3"
curl -sS -H "Authorization: Bearer ${TOKEN}" "http://127.0.0.1:8000/api/yandex/auto-upload"
```

## 7) Следующая рабочая последовательность (без потери контекста)

1. Проверить health watcher/API и базовый API smoke.
2. Доделать zoom в lightbox (изолированно в UI-модуле, без изменений ingestion).
3. Провести 2-3 коротких user-проверки у бильдов, собрать обратную связь.
4. Зафиксировать результат в:
   - `docs/modules/07-ui-ux-bild.md`,
   - `docs/ROADMAP.md`,
   - `docs/deploy-notes.md`.

## 8) Важные ограничения и принятые решения

- Не смешиваем в одном изменении разные модули без явной необходимости.
- Все параметры должны жить в конфиге, без хардкода секретов.
- `config.yaml` и токены не коммитим.
- Legacy-поток через FTP + зеркало Я.Диска держим рабочим параллельно развитию кабинета.
