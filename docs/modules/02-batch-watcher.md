# Модуль 2 — Batch watcher

**Статус:** done  
**Зависимости:** [01-ftp.md](01-ftp.md)

## Что делает на текущем шаге

- Читает `config.yaml` (или `config.example.yaml` для локального прогона).
- Каждые `batch.poll_seconds` проверяет `incoming/*`.
- Если в подпапке фотографа тишина дольше `batch.silence_seconds`:
  - копирует файлы в `backup/<photographer>/<batch_id>/`;
  - переносит файлы в `originals/<event>/<session>/<photographer>/<batch_id>/`;
  - создаёт `batch-manifest.json` с базовой метаинформацией.
- Проверяет JPEG-сигнатуру (SOI/EOI):
  - валидные JPEG идут в пачку;
  - "битые" JPEG переносятся в `backup/<photographer>/<batch_id>/broken/`.
- Пишет в БД:
  - `batches` (включая `broken_files_count`)
  - `photos`
- Создаёт In-App уведомление о новой пачке.
- Отправляет внешние каналы через `Notifier` (если включены).
- При включённом флаге авто-выгрузки Я.Диска отправляет ZIP пачки на Я.Диск.

## Где код

- `src/photofactory/config.py` — загрузка YAML-конфига.
- `src/photofactory/watcher/service.py` — логика сканирования и фиксации пачки.
- `src/photofactory/watcher/cli.py` — CLI-обёртка.

## Запуск

```bash
photofactory-watcher --config config.yaml
```

Однократная проверка (для отладки):

```bash
photofactory-watcher --config config.yaml --run-once --log-level DEBUG
```

## Ограничения текущего шага

- Нет inotify, используется polling.
- Нет полноценной JPEG/EXIF-валидации (используется сигнатурная проверка).
- Нет дедупликации по sha256.
- Нет блокировок для конкурентного запуска (нужно запускать один инстанс).
