# Session Handoff (1-minute context)

## Где мы сейчас

- Ветка: `cursor/init-photofactory-foundation`
- Ядро MVP в проде работает end-to-end:
  - FTP приём (`vsftpd`, upload-only)
  - watcher (`yauza-watcher`, systemd)
  - PostgreSQL + Alembic
  - API (`yauza-api`, JWT auth)
  - кабинет бильда `https://work.yauzamedia.ru/bild`
  - In-App + PWA push
  - Яндекс.Диск зеркало структуры incoming

## Что уже работает end-to-end

1. Камера грузит `incoming/<photographer>/`.
2. Watcher фиксирует пачку после тишины.
3. Файлы попадают в `originals` + `backup`.
4. Пачка/фото пишутся в PostgreSQL (включая `broken_files_count`).
5. В `/bild` видны уведомления, карточки пачек, галерея, кнопки действий.
6. `Скачать пакет` формирует ZIP по шаблону имени.
7. `Загрузить на Я.Диск` и авто-режим работают.
8. Яндекс.Диск путь сейчас: `/Yauza_FTP_Mirror/<photographer>/<filename>.jpg`.

## Внешние каналы

- Telegram: код есть, но на VPS блок исходящего трафика к `api.telegram.org:443`.
- MAX: адаптер готов, но runtime webhook пока не настроен.
- PWA push: рабочий, проверен вручную.

## Критичные runtime-файлы на VPS

- `/etc/yauza/config.yaml` — основной runtime-конфиг
- `/etc/yauza/.db-password` — пароль БД
- `/etc/yauza/.api-auth-password` — пароль API-пользователя `bild`
- `/etc/yauza/pwa_vapid_private.pem` — приватный VAPID ключ

## Команды быстрой проверки (VPS)

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

## Следующий конкретный шаг

- UI/UX доработка кабинета бильда (визуальная иерархия, карточки, мобильный сценарий, упрощение кнопок).
- Параллельно без остановки процесса: legacy-флоу остаётся через FTP + зеркало на Я.Диске.
