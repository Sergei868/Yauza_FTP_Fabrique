# Yauza Photofactory

Серверный конвейер «камера → бильд» для Yauza Media. Разработка **по модулям** с документацией в репозитории.

## С чего начать

1. Прочитайте [PROJECT.md](PROJECT.md) — архитектура и решения.
2. Этапы: [docs/ROADMAP.md](docs/ROADMAP.md).
3. VPS: [docs/VPS-CLEANUP.md](docs/VPS-CLEANUP.md).
4. Скопируйте `config.example.yaml` → `config.yaml` и настройте пути.

## Стек

- Python 3.11+
- FastAPI (API)
- PostgreSQL
- vsftpd
- Telegram (уведомления)

## Локальная разработка (позже)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Скелет кода появится с модулем batch-watcher (фаза 2).

## Cursor

Держите `PROJECT.md` и `docs/` актуальными — так контекст не теряется между сессиями.
