# 🤖 trade-alert-bot

> A Telegram bot that delivers real-time **crypto** and **forex** price alerts straight to your chat.

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)]()

`trade-alert-bot` is a lightweight, production-friendly Telegram bot that watches cryptocurrency and forex markets and pings you the moment a price crosses a level you care about. Built with `python-telegram-bot`, it keeps your alerts in memory (with an optional JSON store), polls free public APIs, and is easy to self-host.

---

## ✨ Features

- 📈 **Crypto prices** — live data from the Binance public API (no API key needed)
- 💱 **Forex rates** — live FX pairs from a free exchange-rate API
- 🔔 **Price alerts** — get notified when a symbol goes **above** or **below** a target
- 🧾 **Alert management** — list, inspect, and remove your active alerts
- ⚡ **On-demand quotes** — fetch the current price of any supported symbol instantly
- 🧠 **Smart polling** — background job checks all alerts on a configurable interval
- 🔒 **Secrets-safe** — all keys live in `.env`, never committed to git
- 🪶 **Minimal footprint** — a single `main.py` entry point and clean module split

---

## 🧰 Tech Stack

| Area | Choice |
|------|--------|
| Language | Python 3.11+ |
| Bot framework | [`python-telegram-bot`](https://python-telegram-bot.org/) (async) |
| HTTP | `requests` |
| Crypto data | Binance public REST API |
| Forex data | openexchangerates / exchangerate.host (free tier) |
| Config | `python-dotenv` |

---

## 📁 Project Structure

```
trade-alert-bot/
├── main.py                 # Entry point — starts the bot
├── bot/
│   ├── __init__.py
│   ├── handlers.py         # Telegram command & message handlers
│   ├── alerts.py           # Alert storage + price-crossing logic
│   └── jobs.py             # Background polling job
├── data/
│   ├── __init__.py
│   ├── fetcher.py          # Crypto + forex price fetchers
│   └── symbols.py          # Symbol normalization & validation
├── config.py               # Loads .env and exposes settings
├── .env.example            # Template — copy to .env and fill in
├── .gitignore
├── requirements.txt
├── LICENSE
└── README.md
```

---

## ✅ Prerequisites

- Python **3.11+**
- A Telegram account
- A Telegram bot token (see below)
- Internet access (the data APIs are public/free)

---

## 🚀 Installation

```bash
# 1. Clone the repo
git clone https://github.com/ImranDev3/trade-alert-bot.git
cd trade-alert-bot

# 2. Create & activate a virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure your secrets
cp .env.example .env      # then edit .env and paste your token
```

---

## 🔑 Get a Telegram Bot Token

1. Open Telegram and search for **[@BotFather](https://t.me/BotFather)**
2. Send `/newbot`
3. Pick a **name** and a **username** (must end in `bot`)
4. BotFather replies with an **HTTP API token** — copy it
5. Paste it into your `.env` as `TELEGRAM_BOT_TOKEN=...`

---

## ⚙️ Configuration (`.env`)

```env
# Required
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ

# Optional
POLL_INTERVAL_SECONDS=60      # how often alerts are checked
ALLOWED_USER_IDS=             # comma-separated Telegram user IDs (blank = allow everyone)
```

---

## ▶️ Usage

```bash
python main.py
```

Open your bot on Telegram, press **Start**, and try the commands below.

### Bot Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Welcome message + help | `/start` |
| `/help` | List all commands | `/help` |
| `/price <SYMBOL>` | Get the current price | `/price BTCUSDT` |
| `/alert <SYMBOL> <above\|below> <PRICE>` | Create an alert | `/alert BTCUSDT above 70000` |
| `/alerts` | List your active alerts | `/alerts` |
| `/remove <ID>` | Remove an alert by ID | `/remove 3` |

### Examples

```
/price ETHUSDT          →  ETH/USDT: $3,512.40
/price EURUSD           →  EUR/USD: 1.0823
/alert BTCUSDT below 65000
/alert EURUSD above 1.10
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

Distributed under the **MIT License**. See [LICENSE](LICENSE) for details.

---

## ⚠️ Disclaimer

This bot is an **educational/technical tool**, not financial advice. Market data may be delayed or inaccurate, and trading carries risk. Always do your own research and never trade money you cannot afford to lose.
