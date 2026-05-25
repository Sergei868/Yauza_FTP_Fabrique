# Модуль 6 — Яндекс.Диск (зеркало файлов)

**Статус:** in_progress  
**Зависимости:** [04-api-web.md](04-api-web.md), [05-telegram.md](05-telegram.md)

## Что реализовано

- Интеграция с Яндекс.Диском через OAuth token (`cloud-api.yandex.net`).
- Ручная выгрузка пачки из кабинета бильда:
  - `POST /api/batches/{batch_id}/upload-yandex`.
  - ответ содержит `uploaded_files` и `remote_path` (папка зеркала).
- Автоматическая выгрузка всех новых пачек:
  - `GET /api/yandex/auto-upload`
  - `POST /api/yandex/auto-upload`
  - состояние хранится в таблице `app_settings` (`yandex_disk.auto_upload_all`).
- Watcher после фиксации пачки проверяет авто-режим и, если включен, копирует файлы пачки (JPEG/RAW) на Я.Диск.
- Структура на Я.Диске (зеркало `incoming`):
  - `<remote_base_path>/<photographer>/<filename>`
- Для бильдов "по-старинке" структура папок на Я.Диске совпадает с FTP-логикой:
  - `incoming/<photographer>/<filename>` <=> `<remote_base_path>/<photographer>/<filename>`

## Конфиг

```yaml
yandex_disk:
  enabled: true
  oauth_token: "YA_OAUTH_TOKEN"
  remote_base_path: /YauzaPhotofactory
```

## Где код

- `src/photofactory/storage/yandex_disk.py` — HTTP-клиент Я.Диска.
- `src/photofactory/watcher/service.py` — авто-выгрузка новых пачек.
- `src/photofactory/api/app.py` — ручная выгрузка + настройка авто-режима.
- `alembic/versions/20260522_0004_add_batch_broken_and_settings.py` — `app_settings`.

## Примечание

- Для production нужно хранить `oauth_token` только в защищённом runtime-конфиге (`/etc/yauza/config.yaml`), не в репозитории.
- В продуктовых сценариях 1+2 зеркало Я.Диска считается основным backup-каналом; локальный `backup/` на сервере делается опциональным через конфиг.
