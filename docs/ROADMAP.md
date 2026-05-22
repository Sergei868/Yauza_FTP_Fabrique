# Дорожная карта

Обновляйте колонку **Статус** по мере выполнения.

## Фаза 0 — фундамент

| Шаг | Описание | Статус |
|-----|----------|--------|
| 0.1 | `PROJECT.md`, `config.example.yaml`, структура `docs/` | done |
| 0.2 | Согласовать путь на VPS (`/srv/yauza/`) | done |
| 0.3 | Очистка VPS ([VPS-CLEANUP.md](VPS-CLEANUP.md)) | done |

## Фаза 1 — FTP

| Шаг | Описание | Статус |
|-----|----------|--------|
| 1.1 | Установка vsftpd, пользователь `upload`, chroot | done |
| 1.2 | Права: upload-only, автосоздание подпапок камерой | done |
| 1.3 | Ручной тест: залить 2–3 JPEG в `incoming/test_cam/` | done |
| Док | [modules/01-ftp.md](modules/01-ftp.md) | done |

## Фаза 2 — Batch watcher

| Шаг | Описание | Статус |
|-----|----------|--------|
| 2.1 | Скелет пакета `src/photofactory/watcher/` | done |
| 2.2 | Таймер тишины 60 с (из config) | done |
| 2.3 | Backup + перенос в originals | done |
| 2.4 | systemd unit `yauza-watcher` | done |
| Док | [modules/02-batch-watcher.md](modules/02-batch-watcher.md) | done |

## Фаза 3 — База данных

| Шаг | Описание | Статус |
|-----|----------|--------|
| 3.1 | PostgreSQL, миграции (Alembic) | done |
| 3.2 | Таблицы: photographers, batches, photos | done |
| Док | [modules/03-database.md](modules/03-database.md) | done |

## Фаза 4 — API и веб для бильда

| Шаг | Описание | Статус |
|-----|----------|--------|
| 4.1 | FastAPI: health, auth (бильд) | done |
| 4.2 | Список пачек, скачать ZIP | done |
| 4.3 | После скачивания — удаление из incoming (если ещё осталось) | done |
| 4.4 | Минимальная страница бильда (`/bild`) | done |
| 4.5 | Кабинет бильда: карточки пачек, галерея, `Скачать пакет` | done |
| Док | [modules/04-api-web.md](modules/04-api-web.md) | done |

## Фаза 5 — Уведомления (In-App / MAX / PWA)

| Шаг | Описание | Статус |
|-----|----------|--------|
| 5.1 | Интерфейс `Notifier`, Telegram + MAX адаптеры | done |
| 5.2 | In-App уведомления: API для колокольчика и автообновления | done |
| 5.3 | Реальная доставка внешнего канала (MAX/Telegram) | in_progress |
| 5.4 | PWA push (дополнительный, опциональный канал) | done |
| 5.5 | UX-финиш `/bild`: unread badge, mark-read, real batch smoke flow | done |
| Док | [modules/05-telegram.md](modules/05-telegram.md) | in_progress |

## Фаза 6 — Яндекс.Диск

| Шаг | Описание | Статус |
|-----|----------|--------|
| 6.1 | OAuth, ручная выгрузка пачки | done |
| 6.2 | Автовыгрузка всех входящих пакетов (настройка в кабинете) | done |
| Док | [modules/06-yandex-disk.md](modules/06-yandex-disk.md) | done |

## Фаза 7 — UI/UX кабинета бильда

| Шаг | Описание | Статус |
|-----|----------|--------|
| 7.1 | Визуальная иерархия: типографика, отступы, читаемость карточек | done |
| 7.2 | Навигация: фильтр/поиск по фотографу и дате, быстрые действия | done |
| 7.3 | Мобильный сценарий: адаптив для телефона и планшета | done |
| 7.4 | UX обработки пачек: явные состояния, прогресс, ошибки, подтверждения | done |
| 7.5 | Просмотр оригинала поверх галереи (lightbox) | done |
| 7.6 | Мини-юзабилити тест с бильдами, фиксация обратной связи | in_progress |
| Док | [modules/07-ui-ux-bild.md](modules/07-ui-ux-bild.md) | in_progress |

## Позже (вне текущего MVP)

Полная картина — в [`reference/legacy-spec.md`](reference/legacy-spec.md). Кратко:

- Валидация JPEG (Pillow), EXIF, дедупликация по sha256
- Превью (small/medium/large), очередь Redis/RQ
- Сессии, мероприятия, разделы, псевдо-сессия «Без сессии»
- Полная ролевая модель: бильд / супербильд / заказчик по токену
- Веб-фронтенд: SPA с кабинетами `/admin`, `/editor`, `/p/<token>`, `/c/<token>`
- Эскалации уведомлений, MAX/SMS/Email/WebPush
- PWA фотографа, архив фотографа
- Публикация в публичный фотобанк yauzamedia.ru (HTTP API)
- Согласование с заказчиком (лайк = одобрено)
