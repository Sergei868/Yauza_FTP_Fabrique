# Подготовка VPS к новому старту

Цель: **безопасно** убрать следы прошлых версий, оставить чистую базу под `yauza-photofactory`, не потерять нужные данные.

## Перед началом

1. **Снимок / бэкап** на стороне хостера (snapshot VPS) — обязательно.
2. Сохраните отдельно, если ещё нужны:
   - старые фото из `incoming` / `originals`;
   - дамп БД;
   - `nginx`/`apache` конфиги доменов;
   - TLS-сертификаты (обычно в `/etc/letsencrypt`).
3. Запишите: ОС (`cat /etc/os-release`), IP, домены, как заходили по SSH.

## Что нужно от вас для помощи через Cursor

Чтобы я мог **выполнить команды на VPS** (а не только дать инструкции), в отдельном сообщении (не в публичный чат, если боитесь утечки):

- хост: `user@IP` или алиас из `~/.ssh/config`;
- ОС (Ubuntu 22.04 / Debian 12 / …);
- что **точно сохранить** (папки, БД, домены).

Без SSH я веду вас по шагам ниже; вы копируете вывод команд в чат — сверяем.

## Шаг 1 — аудит (ничего не удалять)

Подключитесь: `ssh user@your-vps`

```bash
# Система
uname -a
cat /etc/os-release
df -h

# Что слушает порты
sudo ss -tlnp

# Старые сервисы фотофабрики / ftp / web
systemctl list-units --type=service --state=running | grep -iE 'ftp|yauza|photo|gunicorn|uvicorn|nginx|postgres|docker'

# Docker (если был)
docker ps -a 2>/dev/null || true

# Типичные каталоги — подставьте свои пути если помните
sudo ls -la /srv/ /opt/ /var/www/ 2>/dev/null
sudo find /srv /opt /var/www -maxdepth 3 -type d 2>/dev/null | head -80
```

Пришлите вывод — отметим, что удалять, что оставить.

## Шаг 2 — остановить старые сервисы

```bash
# Примеры имён — замените на реальные из шага 1
sudo systemctl stop vsftpd proftpd nginx yauza-watcher yauza-api 2>/dev/null
sudo systemctl disable vsftpd proftpd yauza-watcher yauza-api 2>/dev/null

# Docker-стек прошлой версии (если был)
cd /path/to/old/compose && sudo docker compose down -v  # только если уверены!
```

## Шаг 3 — архив и удаление старого кода

```bash
sudo mkdir -p /root/archive-pre-2026
sudo tar -czf /root/archive-pre-2026/old-srv-$(date +%Y%m%d).tar.gz /srv/yauza /opt/yauza 2>/dev/null || true
# Проверьте размер архива
ls -lh /root/archive-pre-2026/
```

После проверки архива:

```bash
# Удаление — только после подтверждения что архив ок
sudo rm -rf /srv/yauza/incoming/*   # если фото уже не нужны
sudo rm -rf /opt/yauza-old          # пример
```

## Шаг 4 — чистая структура под новый проект

```bash
sudo mkdir -p /srv/yauza/{incoming,originals,backup}
sudo groupadd -f yauza
sudo useradd -r -g yauza -d /srv/yauza -s /usr/sbin/nologin upload 2>/dev/null || true
sudo chown -R upload:yauza /srv/yauza
sudo chmod 775 /srv/yauza/incoming
sudo chmod 750 /srv/yauza/originals /srv/yauza/backup
```

## Шаг 5 — PostgreSQL

Если Postgres нужен заново:

```bash
# Только если старая БД не нужна — сначала дамп!
sudo -u postgres pg_dumpall > /root/archive-pre-2026/pg-all.sql

# Или удалить только старую БД:
sudo -u postgres psql -c "\l"
# sudo -u postgres dropdb old_db_name;
```

Новая БД будет создана на этапе 3 ([ROADMAP.md](ROADMAP.md)).

## Шаг 6 — firewall

```bash
sudo ufw status
# Открыть: 22 (SSH), 80/443 (веб), 21 + passive FTP (диапазон пассивных портов — на этапе FTP)
```

## Шаг 7 — деплой новой версии (позже)

1. Клонировать репозиторий в `/opt/yauza-photofactory`
2. `config.yaml` на сервере (секреты)
3. systemd units: `yauza-watcher`, `yauza-api`
4. vsftpd по [modules/01-ftp.md](modules/01-ftp.md)

## Чеклист «готов к этапу 1»

- [ ] Snapshot VPS сделан
- [ ] Старые сервисы остановлены
- [ ] Архив `/root/archive-pre-2026/` проверен
- [ ] `/srv/yauza/{incoming,originals,backup}` созданы
- [ ] Пользователь `upload` существует
- [ ] Вывод аудита (шаг 1) сохранён в `docs/deploy-notes.md` (по желанию)
