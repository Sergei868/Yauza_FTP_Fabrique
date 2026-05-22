# Модуль 3 — База данных (PostgreSQL + Alembic)

**Статус:** done  
**Зависимости:** [02-batch-watcher.md](02-batch-watcher.md)

## Что реализовано

- PostgreSQL развёрнут на VPS.
- Добавлена схема MVP с таблицами:
  - `photographers`
  - `batches`
  - `photos`
  - `notifications`
  - `push_subscriptions`
  - `app_settings`
- Добавлен Alembic:
  - `alembic.ini`
  - `alembic/env.py`
  - миграция `20260522_0001_create_core_tables.py`
- Watcher теперь пишет в БД:
  - при новой папке создаёт `photographers.folder_name`
  - при фиксации пачки создаёт запись в `batches` (включая `broken_files_count`)
  - файлы пачки пишет в `photos`
  - создаёт In-App уведомление в `notifications`
- Настройки runtime-флагов (например, авто-выгрузка на Я.Диск) хранятся в `app_settings`.

## Где код

- Модели: `src/photofactory/db/models.py`
- Сессии/движок: `src/photofactory/db/session.py`
- Репозиторий: `src/photofactory/db/repository.py`
- Интеграция в watcher: `src/photofactory/watcher/service.py`
- Alembic env: `alembic/env.py`

## Runtime-конфиг на сервере

- Конфиг вынесен в `/etc/yauza/config.yaml` (вне каталога кода, чтобы не удалялся при `rsync --delete`).
- Пароль БД хранится в `/etc/yauza/.db-password`.
- `yauza-watcher.service` использует `--config /etc/yauza/config.yaml`.

## Проверка

1. Выполнить миграции:

```bash
PHOTOFACTORY_CONFIG=/etc/yauza/config.yaml alembic upgrade head
```

2. Проверить таблицы:

```bash
psql -h 127.0.0.1 -U photofactory -d photofactory -c '\dt'
```

3. Smoke-тест watcher:

- положить `*.JPG` в новую подпапку `incoming/<name>/`
- дождаться фиксации пачки
- убедиться, что записи появились в `batches` и `photos`

## Что дальше

1. Добавить полноценные флаги качества файлов (EXIF/Pillow-проверки, не только сигнатуры).
2. Добавить служебную таблицу статусов выгрузки в внешние каналы (если потребуется аудит по каждой попытке).
