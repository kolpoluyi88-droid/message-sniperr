# 🎯 Message Sniper Bot — Полная инструкция по деплою

## Содержание
1. [Что нужно для запуска](#1-что-нужно-для-запуска)
2. [Подготовка токенов](#2-подготовка-токенов)
3. [Запуск через Docker](#3-запуск-через-docker)
4. [Запуск без Docker (bare metal)](#4-запуск-без-docker)
5. [Настройка CryptoBot](#5-настройка-cryptobot)
6. [Добавление аккаунтов-отправителей](#6-добавление-аккаунтов-отправителей)
7. [Тарифы и настройка цен](#7-тарифы-и-настройка-цен)
8. [Мониторинг и логи](#8-мониторинг-и-логи)
9. [FAQ и частые ошибки](#9-faq)

---

## 1. Что нужно для запуска

| Компонент | Минимум | Рекомендуется |
|-----------|---------|---------------|
| ОС | Ubuntu 20.04 | Ubuntu 22.04 LTS |
| RAM | 512 MB | 2 GB |
| CPU | 1 vCPU | 2 vCPU |
| Диск | 5 GB | 20 GB |
| Docker | ✅ | ✅ |
| Python | 3.11+ | 3.11+ |

**Хостинг:** Любой VPS/VDS. Рекомендуется Hetzner, DigitalOcean, TimeWeb.

---

## 2. Подготовка токенов

### 2.1 Токен бота (BotFather)
```
1. Открыть @BotFather в Telegram
2. /newbot → введите имя: Message Sniper
3. username: MessageSniperBot (или любой свободный)
4. Скопировать токен вида: 1234567890:ABCdef...
```

### 2.2 Telethon API (для отправки сообщений)
```
1. Перейти на https://my.telegram.org
2. Войти своим номером телефона
3. API development tools → Create new application
4. App title: MessageSniper, Platform: Other
5. Скопировать api_id (число) и api_hash (строка)
6. Вставить в файл scheduler/tasks.py:
   TELETHON_API_ID = 12345
   TELETHON_API_HASH = "abcdef..."
```

### 2.3 CryptoBot токен
```
1. Открыть @CryptoBot в Telegram
2. My Apps → Create App
3. Название: Message Sniper
4. Скопировать API Token
```

### 2.4 TON кошелёк (опционально)
```
1. Установить Tonkeeper или @wallet
2. Создать кошелёк, скопировать адрес (UQ...)
3. Вставить в .env → TON_WALLET_ADDRESS
```

---

## 3. Запуск через Docker (рекомендуется)

### Шаг 1: Клонировать/загрузить проект
```bash
# Загрузить на сервер (через scp или git)
scp -r message_sniper/ user@your-server:/opt/message_sniper
cd /opt/message_sniper
```

### Шаг 2: Установить Docker
```bash
curl -fsSL https://get.docker.com | sh
apt install docker-compose-plugin -y
```

### Шаг 3: Настроить переменные окружения
```bash
cp .env.example .env
nano .env
```

Заполните обязательные поля:
```env
BOT_TOKEN=ваш_токен_от_BotFather
ADMIN_IDS=[ваш_telegram_id]
CRYPTO_BOT_TOKEN=токен_от_CryptoBot
TON_WALLET_ADDRESS=ваш_TON_адрес
```

> Узнать свой Telegram ID: написать @userinfobot

### Шаг 4: Запустить
```bash
docker compose up -d --build
```

### Шаг 5: Проверить работу
```bash
docker compose logs -f bot
```

Бот запущен ✅ — напишите /start своему боту.

---

## 4. Запуск без Docker

```bash
# Установить зависимости
apt update && apt install python3.11 python3-pip redis-server -y

# Клонировать проект
cd /opt/message_sniper

# Создать виртуальное окружение
python3.11 -m venv venv
source venv/bin/activate

# Установить библиотеки
pip install -r requirements.txt

# Настроить .env
cp .env.example .env
nano .env

# Запустить Redis
systemctl start redis

# Запустить бот
python main.py
```

### Автозапуск через systemd
```bash
nano /etc/systemd/system/message_sniper.service
```

```ini
[Unit]
Description=Message Sniper Bot
After=network.target redis.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/message_sniper
ExecStart=/opt/message_sniper/venv/bin/python main.py
Restart=always
RestartSec=5
EnvironmentFile=/opt/message_sniper/.env

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable message_sniper
systemctl start message_sniper
```

---

## 5. Настройка CryptoBot

CryptoBot автоматически создаёт invoice и принимает оплату.  
Бот проверяет статус при нажатии «Проверить оплату».

**Поддерживаемые монеты:** USDT, TON, BTC, ETH, USDC, BNB

Если хотите убрать какую-то монету — отредактируйте в `config.py`:
```python
SUPPORTED_COINS = ["USDT", "TON", "BTC"]  # оставьте нужные
```

---

## 6. Добавление аккаунтов-отправителей

Аккаунты добавляются **через бота** — меню «Мои аккаунты» → «Добавить аккаунт».

**Требования к аккаунтам:**
- Аккаунт должен состоять в группах, куда планируется рассылка
- Аккаунту желательно быть >30 дней (молодые быстрее банятся)
- Рекомендуется: 1 аккаунт на 50-100 групп

**Ротация аккаунтов** происходит автоматически между группами.

**FloodWait:** при получении ограничения аккаунт автоматически помечается как заблокированный, рассылка продолжается с другого аккаунта.

---

## 7. Тарифы и настройка цен

Редактировать в `config.py`:

```python
TARIFF_PLANS = {
    "starter": {
        "name": "🥉 Starter",
        "messages": 100,
        "price_usd": 4.99,      # ← цена в USD
        ...
    },
    "pro": {
        "messages": 2000,
        "price_usd": 59.99,     # ← измените под себя
        ...
    }
}
```

После изменения — перезапустить бот:
```bash
docker compose restart bot
```

---

## 8. Мониторинг и логи

### Логи в реальном времени
```bash
docker compose logs -f bot
```

### Последние 100 строк
```bash
docker compose logs --tail=100 bot
```

### Файл логов
```bash
tail -f /opt/message_sniper/logs/bot.log
```

### Перезапуск бота
```bash
docker compose restart bot
```

### Полная остановка
```bash
docker compose down
```

### Обновление после изменений кода
```bash
docker compose up -d --build
```

---

## 9. FAQ

**Q: Бот не запускается — ошибка токена**
```
A: Проверьте BOT_TOKEN в .env. Должен быть без кавычек.
```

**Q: CryptoBot не принимает платежи**
```
A: Убедитесь что CRYPTO_BOT_TOKEN правильный.
   Проверьте: https://pay.crypt.bot/api/getMe с вашим токеном
```

**Q: FloodWait ошибки при рассылке**
```
A: Это нормально. Добавьте больше аккаунтов-отправителей.
   Увеличьте DELAY_BETWEEN_MESSAGES в .env до 3-5 секунд.
```

**Q: Аккаунт SESSION_EXPIRED**
```
A: Зайдите в бот → Мои аккаунты → Удалите старый → Добавьте снова
```

**Q: Рассылка идёт медленно**
```
A: Задержка 2.5 секунды — это защита от бана.
   Добавьте больше аккаунтов — они работают параллельно.
```

**Q: Как добавить PostgreSQL вместо SQLite?**
```
A: В .env измените:
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/sniper
И добавьте в docker-compose.yml сервис postgres.
```

---

## Структура проекта

```
message_sniper/
├── main.py                    # Точка входа
├── config.py                  # Настройки и тарифы
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── bot/
│   ├── handlers/
│   │   ├── start.py           # /start, онбординг, рефералы
│   │   ├── account.py         # Аккаунт пользователя, Telethon сессии
│   │   ├── campaigns.py       # Создание и управление рассылками
│   │   ├── payment.py         # CryptoBot, прямой TON
│   │   └── admin.py           # Панель администратора
│   ├── keyboards/             # InlineKeyboard для каждого модуля
│   └── middlewares/
│       ├── auth.py            # Авторизация, бан
│       └── throttling.py      # Антиспам
├── database/
│   └── db.py                  # SQLAlchemy модели: User, Campaign, Payment...
└── scheduler/
    └── tasks.py               # APScheduler + Telethon движок рассылки
```

---

## Контакты и поддержка

Настройте поддержку в `bot/handlers/start.py`:
```python
"<b>Поддержка:</b> @YourSupportUsername"
```

---

*Message Sniper v1.0 — Professional Telegram Bulk Messaging Service*
