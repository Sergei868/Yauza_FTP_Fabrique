# Аварийное восстановление (код + БД + runtime)

Этот чеклист нужен для быстрого отката к зафиксированному checkpoint.

Текущий эталонный checkpoint:

- git tag: `pre-audit-20260524-1630`
- VPS backup dir: `/var/backups/yauza/checkpoints/20260524_132959`
- локальный bundle: `backups/checkpoints/20260524_162209/pre-audit.bundle`

## 1) Подключиться и проверить backup

```bash
ssh photoflow@138.16.224.55
sudo ls -lh /var/backups/yauza/checkpoints/20260524_132959
cd /var/backups/yauza/checkpoints/20260524_132959
sudo sha256sum -c SHA256SUMS.txt
```

Ожидаемо: для всех файлов статус `OK`.

## 2) Остановить сервисы перед откатом

```bash
sudo systemctl stop yauza-api yauza-watcher
```

## 3) Откатить код к checkpoint tag

```bash
cd /opt/yauza-photofactory
git fetch --all --tags
git checkout pre-audit-20260524-1630
```

## 4) Восстановить runtime-конфиг и unit-файлы

```bash
sudo cp /var/backups/yauza/checkpoints/20260524_132959/config.yaml /etc/yauza/config.yaml
sudo cp /var/backups/yauza/checkpoints/20260524_132959/yauza-api.service /etc/systemd/system/yauza-api.service
sudo cp /var/backups/yauza/checkpoints/20260524_132959/yauza-watcher.service /etc/systemd/system/yauza-watcher.service
sudo systemctl daemon-reload
```

## 5) Восстановить БД из дампа

```bash
sudo -u postgres pg_restore --clean --if-exists --no-owner --dbname=photofactory /var/backups/yauza/checkpoints/20260524_132959/db.dump
```

## 6) Запустить сервисы и проверить здоровье

```bash
sudo systemctl start yauza-api yauza-watcher
sudo systemctl status yauza-api --no-pager -n 30
sudo systemctl status yauza-watcher --no-pager -n 30
```

## 7) Быстрый smoke API

```bash
API_PASS=$(sudo awk -F": " '/^  password:/{print $2; exit}' /etc/yauza/config.yaml)
TOKEN=$(curl -sS -X POST http://127.0.0.1:8000/api/auth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=bild' \
  --data-urlencode "password=${API_PASS}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -sS -H "Authorization: Bearer ${TOKEN}" "http://127.0.0.1:8000/api/batches?limit=2"
```

## 8) Если удалён origin/репозиторий: восстановить код из bundle

На локальной машине:

```bash
git clone backups/checkpoints/20260524_162209/pre-audit.bundle yauza-photofactory-restore
cd yauza-photofactory-restore
git checkout pre-audit-20260524-1630
```
