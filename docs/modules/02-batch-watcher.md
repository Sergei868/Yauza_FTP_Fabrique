# Модуль 2 — Batch watcher

**Статус:** in_progress  
**Зависимости:** [01-ftp.md](01-ftp.md)

## Что делает на текущем шаге

- Читает `config.yaml` (или `config.example.yaml` для локального прогона).
- Каждые `batch.poll_seconds` проверяет `incoming/*`.
- Если в подпапке фотографа тишина дольше `batch.silence_seconds`:
  - копирует поддерживаемые файлы (JPEG + RAW из `batch.allowed_extensions`) в `originals/<event>/<session>/<photographer>/<batch_id>/` (без удаления из `incoming`);
  - при включённом флаге backup дополнительно пишет в `backup/<photographer>/<batch_id>/`;
  - создаёт `batch-manifest.json` с базовой метаинформацией.
- Проверяет JPEG-сигнатуру (SOI/EOI) только для JPEG:
  - валидные JPEG идут в пачку;
  - "битые" JPEG считаются в `broken_files_count` и не попадают в пакет.
- RAW-файлы из `allowed_extensions` добавляются в пакет без JPEG-сигнатурной проверки.
- Пишет в БД:
  - `batches` (включая `broken_files_count`)
  - `photos`
- Создаёт In-App уведомление о новой пачке.
- Отправляет внешние каналы через `Notifier` (если включены).
- При включённом флаге авто-выгрузки Я.Диска зеркалирует файлы пачки в `<remote_base_path>/<photographer>/`.

## Обновление продуктового режима (сценарии 1+2)

- `incoming` больше не очищается watcher'ом после фиксации пачки.
- Чтобы файлы не попадали в повторные пачки, watcher фиксирует только "новую волну" файлов после предыдущей фиксации (по внутренней метке последней обработки).
- Очистка `incoming` переносится на действия бильда:
  - вручную (FileZilla),
  - или кнопками скачивания в кабинете (`Скачать все` / `Скачать выбранное`).

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
