# Модуль 1 — FTP (vsftpd)

**Статус:** не начат  
**Зависимости:** [VPS-CLEANUP.md](../VPS-CLEANUP.md)

## Требование бизнеса

- Один логин/пароль на всё дерево `incoming/`.
- Фотограф идентифицируется **именем подпапки**, которое задаётся в камере.
- Подпапка **не создаётся заранее** на сервере — камера создаёт её при первой заливке.
- Upload-only, chroot, без TLS (ограничение камер).

## Модель доступа

```
FTP user: upload  →  chroot: /srv/yauza/incoming
                      ├── ivanov/     ← имя с камеры
                      ├── petrov/
                      └── sidorov/
```

Все фотографы используют **один пароль** мероприятия (ротация пароля — операционная процедура супербильда).

## vsftpd (черновик настроек)

Файл `/etc/vsftpd.conf` (финальные значения — после теста на VPS):

- `local_enable=YES`
- `write_enable=YES`
- `chroot_local_user=YES`
- `allow_writeable_chroot=YES` (или отдельный layout без записи в корень chroot — предпочтительнее subdirs-only)
- Пользователь `upload`: домашний каталог = `/srv/yauza/incoming`
- Запрет DELETE/RENAME для upload-only — через `vsftpd` ACL или отдельный wrapper (уточнить на этапе реализации)

## Пассивный режим

Камеры за NAT — на VPS открыть диапазон `ftp.passive_port_min`–`max` из `config.yaml` в firewall и в vsftpd.

## Тест приёмки

1. FileZilla: хост, пользователь `upload`, пароль из config.
2. Залить `test1.jpg` в подпапку `test_cam/` (создать подпапку в клиенте как делает камера).
3. Файл виден на сервере в `/srv/yauza/incoming/test_cam/`.
4. Попытка удалить файл с FTP — должна **не** проходить.

## Безопасность

- Сильный пароль, смена после мероприятия.
- По возможности `ufw allow from PHOTOGRAPHER_SUBNET to any port 21,40000:40050`.
- Мониторинг размера `incoming/`.

## Следующий модуль

После успешного теста → [02-batch-watcher.md](02-batch-watcher.md).
