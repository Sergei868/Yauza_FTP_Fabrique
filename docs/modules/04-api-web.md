# Модуль 4 — API и веб-слой для бильда (MVP API)

**Статус:** in_progress  
**Зависимости:** [03-database.md](03-database.md)

## Что сделано в этом шаге

- Поднят базовый FastAPI backend поверх PostgreSQL.
- Реализованы endpoints:
  - `GET /health`
  - `POST /api/auth/token` (логин бильда, выдача JWT)
  - `GET /api/auth/me` (роль текущего пользователя)
  - `GET /api/batches?limit=...`
  - `GET /api/batches/{batch_id}`
  - `GET /api/batches/{batch_id}/download`
- Эндпоинт скачивания формирует ZIP из актуальных файлов пакета и удаляет их из `incoming` после успешной выдачи.
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
  - галерея файлов внутри карточки пачки:
    - JPEG показываются превью,
    - RAW показываются как плитка-заглушка `RAW` (без превью) с сохранением действий скачивания.
  - кнопка `Скачать все` (архив именуется по шаблону `<photographer>-<DD>-<MM>-<HHMM>-<daily_seq>.zip`).
  - кнопка `Скачать выбранное` (ZIP только отмеченных фото; имя `<photographer>-<DD>-<MM>-<HHMM>-selected_<daily_counter>-<daily_seq>.zip`).
  - чекбоксы выбора фото в карточке пакета.
  - кнопка `Загрузить на Я.Диск`.
  - чекбокс `Загружать все входящие пакеты на Я.Диск`.
- Добавлен endpoint просмотра фото:
  - `GET /api/photos/{photo_id}/content`.
- Добавлены endpoints для Я.Диска:
  - `POST /api/batches/{batch_id}/upload-yandex`;
  - `GET /api/yandex/auto-upload`;
  - `POST /api/yandex/auto-upload`.
- Добавлен admin-only контур настроек:
  - `GET /api/admin/settings`
  - `POST /api/admin/settings`
  - в UI при входе под admin показывается секция администрирования:
    - логин/пароль бильда,
    - логин/пароль admin,
    - логин/пароль FTP-бильда,
    - логин/пароль FTP-фотографа,
    - OAuth токен и путь зеркала Я.Диска.

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

1. Я.Диск требует корректный OAuth token в runtime-конфиге.
2. Роли `bild/admin` пока без отдельной user-таблицы; учетные данные и сервисные секреты хранятся в `app_settings`.
3. Скрытие "неактуальных" пакетов реализуется по факту наличия файлов в `incoming`.
4. FTP-учетки в admin-секции пока управляются как runtime-настройки приложения; автоматическое применение в системный `vsftpd` будет отдельным шагом.
