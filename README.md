# «Во что?» — Steam Party Telegram Bot

MVP Telegram-бота для компаний друзей. Бот связывает Telegram с публичными Steam-профилями, находит общие игры участников, создаёт лобби с голосованием и присылает уведомления о скидках.

## Возможности

- привязка Steam по SteamID или ссылке на профиль;
- синхронизация публичной библиотеки и игрового времени;
- карточка профиля и статус участников группы;
- поиск общих игр;
- лобби: сбор участников → три игры → голосование → победитель;
- персональный список игр со скидочным порогом 25%, 50% или 75%;
- отдельный фоновый worker для проверки магазина.

## Команды

```text
/link <SteamID или ссылка>   привязать Steam
/sync                        обновить библиотеку
/profile                     показать свой профиль
/online                      статусы участников группы
/common                      общие игры группы
/lobby                       создать лобби
/watch <AppID> <25|50|75>    следить за скидкой
/watchlist                   список уведомлений
/unwatch <AppID>             перестать следить
```

## Локальный запуск

Нужны Docker и Docker Compose.

1. Создайте бота через [@BotFather](https://t.me/BotFather).
2. Получите [Steam Web API key](https://steamcommunity.com/dev/apikey).
3. Скопируйте настройки:

```bash
cp .env.example .env
```

4. Заполните `BOT_TOKEN`, `STEAM_API_KEY` и задайте надёжный `POSTGRES_PASSWORD`. Пароль в `DATABASE_URL` должен совпадать.
5. Запустите:

```bash
docker compose up -d --build
docker compose logs -f bot worker
```

Бот работает через long polling: домен, TLS-сертификат и открытый входящий порт не нужны.

## Развёртывание на Hetzner

Подойдёт обычный Ubuntu VPS с Docker Compose и минимум 1 GB RAM.

```bash
git clone <URL_РЕПОЗИТОРИЯ> vochto-bot
cd vochto-bot
cp .env.example .env
nano .env
docker compose up -d --build
docker compose ps
```

Обновление:

```bash
git pull --ff-only
docker compose up -d --build
```

PostgreSQL не публикуется наружу. Данные хранятся в Docker volume `postgres_data`.

## Архитектура

```text
bot     aiogram long polling и Telegram-команды
worker  периодическая проверка скидок
db      PostgreSQL
migrate Alembic перед запуском приложений
```

Это модульный монолит: оба процесса используют общий код и одну базу данных.

## Разработка без Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e . pytest pytest-asyncio respx ruff pyright
ruff check .
pytest
pyright
```

На Windows активация окружения: `.venv\Scripts\Activate.ps1`.
