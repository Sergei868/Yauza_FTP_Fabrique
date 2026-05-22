# Модуль 4 — API и веб-слой для бильда (MVP API)

**Статус:** done  
**Зависимости:** [03-database.md](03-database.md)

## Что сделано в этом шаге

- Поднят базовый FastAPI backend поверх PostgreSQL.
- Реализованы endpoints:
  - `GET /health`
  - `POST /api/auth/token` (логин бильда, выдача JWT)
  - `GET /api/batches?limit=...`
  - `GET /api/batches/{batch_id}`
  - `GET /api/batches/{batch_id}/download`
- Эндпоинт скачивания формирует ZIP из `originals` и может удалить остатки в `incoming` (`cleanup_incoming=true`).
- Endpoints `/api/batches*` защищены Bearer JWT.
- Добавлена минимальная «боевая» страница бильда:
  - `GET /bild`
  - логин (JWT),
  - колокольчик In-App (polling `/api/notifications`),
  - включение/отключение push и test push.
  - кнопка «Проверка реальной пачкой» (`POST /api/dev/smoke-batch`).
  - кнопка «Пометить прочитанными» (`POST /api/notifications/mark-read`).
  - список пачек с метаданными:
    - фотограф,
    - время загрузки,
    - количество снимков,
    - количество битых файлов,
    - порядковый номер пачки за сутки.
  - галерея JPEG внутри карточки пачки.
  - кнопка `Скачать пакет` (архив именуется по шаблону `<photographer>_<date>_<time>_<daily_seq>.zip`).
  - кнопка `Загрузить на Я.Диск`.
  - чекбокс `Загружать все входящие пакеты на Я.Диск`.
- Добавлен endpoint просмотра фото:
  - `GET /api/photos/{photo_id}/content`.
- Добавлены endpoints для Я.Диска:
  - `POST /api/batches/{batch_id}/upload-yandex`;
  - `GET /api/yandex/auto-upload`;
  - `POST /api/yandex/auto-upload`.

## Где код

- `src/photofactory/api/app.py` — приложение и роуты
- `src/photofactory/api/schemas.py` — response-схемы
- `src/photofactory/api/cli.py` — запуск uvicorn из конфига
- `src/photofactory/api/static/bild-dashboard.html`
- `src/photofactory/api/static/bild-dashboard.js`

## Запуск

```bash
photofactory-api --config /etc/yauza/config.yaml
```

## Ограничения текущего шага

1. Галерея без клиентских превью-генераторов (показываются оригиналы JPEG).
2. Я.Диск требует корректный OAuth token в runtime-конфиге.
3. Модель пользователей бильдов пока конфиговая (`config.yaml`), без ролей в БД.
