# Дорожная карта

Обновляйте колонку **Статус** по мере выполнения.

## Фаза 0 — фундамент

| Шаг | Описание | Статус |
|-----|----------|--------|
| 0.1 | `PROJECT.md`, `config.example.yaml`, структура `docs/` | done |
| 0.2 | Согласовать путь на VPS (`/srv/yauza/`) | todo |
| 0.3 | Очистка VPS ([VPS-CLEANUP.md](VPS-CLEANUP.md)) | todo |

## Фаза 1 — FTP

| Шаг | Описание | Статус |
|-----|----------|--------|
| 1.1 | Установка vsftpd, пользователь `upload`, chroot | todo |
| 1.2 | Права: upload-only, автосоздание подпапок камерой | todo |
| 1.3 | Ручной тест: залить 2–3 JPEG в `incoming/test_cam/` | todo |
| Док | [modules/01-ftp.md](modules/01-ftp.md) | todo |

## Фаза 2 — Batch watcher

| Шаг | Описание | Статус |
|-----|----------|--------|
| 2.1 | Скелет пакета `src/photofactory/watcher/` | todo |
| 2.2 | Таймер тишины 60 с (из config) | todo |
| 2.3 | Backup + перенос в originals | todo |
| 2.4 | systemd unit `yauza-watcher` | todo |
| Док | [modules/02-batch-watcher.md](modules/02-batch-watcher.md) | todo |

## Фаза 3 — База данных

| Шаг | Описание | Статус |
|-----|----------|--------|
| 3.1 | PostgreSQL, миграции (Alembic) | todo |
| 3.2 | Таблицы: photographers, batches, photos | todo |
| Док | [modules/03-database.md](modules/03-database.md) | todo |

## Фаза 4 — API и веб для бильда

| Шаг | Описание | Статус |
|-----|----------|--------|
| 4.1 | FastAPI: health, auth (бильд) | todo |
| 4.2 | Список пачек, скачать ZIP | todo |
| 4.3 | После скачивания — удаление из incoming (если ещё осталось) | todo |
| Док | [modules/04-api-web.md](modules/04-api-web.md) | todo |

## Фаза 5 — Telegram

| Шаг | Описание | Статус |
|-----|----------|--------|
| 5.1 | Интерфейс `Notifier`, реализация Telegram | todo |
| 5.2 | Сообщение: фотограф, кол-во файлов, ссылка на веб | todo |
| Док | [modules/05-telegram.md](modules/05-telegram.md) | todo |

## Фаза 6 — Яндекс.Диск

| Шаг | Описание | Статус |
|-----|----------|--------|
| 6.1 | OAuth, загрузка папки пачки | todo |
| 6.2 | Очередь, статус в БД | todo |
| Док | [modules/06-yandex-disk.md](modules/06-yandex-disk.md) | todo |

## Позже (вне текущего MVP)

- Сессии, мероприятия, PWA фотографа
- Супербильд, заказчик по токену
- Публикация в публичный фотобанк
- MAX как второй Notifier
