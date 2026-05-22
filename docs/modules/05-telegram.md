# Модуль 5 — Уведомления (In-App / MAX / PWA)

**Статус:** in_progress  
**Зависимости:** [04-api-web.md](04-api-web.md)

## Что реализовано

- Добавлен единый интерфейс уведомлений (`Notifier`) и мультиканальный `CompositeNotifier`.
- Реализованы адаптеры:
  - Telegram (`sendMessage` через Bot API)
  - MAX (webhook-провайдер, JSON payload)
- После фиксации пачки watcher:
  - записывает In-App уведомление в таблицу `notifications`;
  - отправляет внешние каналы через notifier (если включены в конфиг).
- Добавлен `NullNotifier` fallback (если каналы не настроены/выключены).
- Добавлен API endpoint для колокольчика:
  - `GET /api/notifications` (JWT protected).
- Добавлена backend-база для PWA push:
  - таблица `push_subscriptions`;
  - `GET /api/pwa/public-key`;
  - `POST /api/pwa/subscriptions`;
  - `DELETE /api/pwa/subscriptions`.
- Добавлена тестовая PWA-страница для телефона:
  - `GET /pwa/test` (HTML)
  - `GET /pwa-test.js`
  - `GET /sw.js` (Service Worker)
  - `POST /api/pwa/test-push`

## Где код

- `src/photofactory/notifications/base.py`
- `src/photofactory/notifications/telegram.py`
- `src/photofactory/notifications/max.py`
- `src/photofactory/notifications/factory.py`
- `src/photofactory/watcher/service.py` (вызов после фиксации пачки)
- `src/photofactory/api/app.py` (`/api/notifications`)
- `src/photofactory/api/static/pwa-test.html`
- `src/photofactory/api/static/pwa-test.js`
- `src/photofactory/api/static/sw.js`
- `alembic/versions/20260522_0002_add_notifications_table.py`
- `alembic/versions/20260522_0003_add_push_subscriptions.py`

## Конфиг

```yaml
notifications:
  enabled: true
  channels:
    - telegram
    - max
    # - pwa
  telegram:
    bot_token: "123456:ABC-..."
    default_chat_id: "-1001234567890"
  max:
    webhook_url: "https://max.example.com/incoming/webhook"
    auth_token: "OPTIONAL_BEARER_TOKEN"
  pwa:
    enabled: true
    vapid_public_key: "BEl...."        # публичный VAPID ключ для клиента
    vapid_private_key: "6f4..."        # приватный VAPID ключ только на сервере
    vapid_subject: "mailto:admin@yauza-media.ru"
```

## Шаблон сообщения (MVP)

- фотограф
- ключ пачки
- число фото
- суммарный размер
- ссылка на API детали пачки

## Что осталось для закрытия модуля

1. Подключить рабочий внешний канал:
   - MAX webhook (предпочтительно), или Telegram при доступной сети.
2. Проверить реальную доставку сообщения в редакционный чат.
3. Для PWA push: подключить реальные VAPID ключи и клиентский Service Worker в фронтенде.

## Текущее состояние на VPS

- VAPID ключи уже сгенерированы и подключены.
- Backend готов принимать подписки и отправлять тестовый push.
- Клиентская test-страница (`/pwa/test`) подключена: Service Worker + subscribe/unsubscribe + test push.

## Подтверждённый результат (iPhone)

- Подписка устройства сохраняется в backend (`/api/pwa/subscriptions`).
- Тестовый push уходит успешно (`sent=1, failed=0, deactivated=0`).
- Уведомление на iPhone получено (проверено вручную).
