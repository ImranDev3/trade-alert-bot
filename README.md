# 🤖 trade-alert-bot

> A Telegram bot that delivers real-time **crypto** and **forex** price alerts straight to your chat.

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)]()

`trade-alert-bot` is a lightweight, production-friendly Telegram bot that watches cryptocurrency and forex markets and pings you the moment a price crosses a level you care about. Built with `python-telegram-bot`, it keeps your alerts in memory (with an optional JSON store), polls free public APIs, and is easy to self-host.

---

## ✨ Features

- 📈 **Realtime crypto prices** — streamed live from the Binance WebSocket (no API key), with a price cache and automatic REST fallback
- 💱 **Realtime forex rates** — near-realtime FX from Yahoo Finance, with a Frankfurter (ECB) fallback
- 🔔 **Price-level alerts** — get notified when a symbol goes **above** or **below** a target
- 📊 **Percentage-move alerts** — `/alert BTCUSDT up 5%` fires when the price moves N% from a captured baseline
- 👀 **Watchlists** — track a set of symbols; the bot broadcasts their live prices on a schedule and streams the crypto ones over WebSocket
- 🗓️ **Daily market summary** — a once-a-day digest of your watchlist at a time you choose
- 📰 **Auto news drops (important only)** — opt in and the bot pushes the headlines that actually matter, from Cointelegraph, CoinDesk, Decrypt & Bitcoin News. Each user only gets headlines that score as important — high-signal topics (ETF, SEC, hacks, crashes, listings, partnerships…) **or** mention a symbol on their watchlist. Dedup ensures nothing repeats
- 💥 **Large-liquidation alerts** — set a USD threshold and the bot pings you the moment a forced liquidation worth that much hits Binance (long/short, size, price), streamed live
- 🧾 **Alert management** — list, inspect, and remove your active alerts
- ⚡ **On-demand quotes** — fetch the current price of any supported symbol instantly
- 🧠 **Background jobs** — alert polling, watchlist updates, news drops, and the daily digest all run automatically
- 🔒 **Secrets-safe** — all keys live in `.env`, never committed to git
- 🪶 **Clean module split** — realtime layer, data fetchers, and bot logic kept separate

---

## 🧰 Tech Stack

| Area | Choice |
|------|--------|
| Language | Python 3.11+ (tested on 3.14) |
| Bot framework | [`python-telegram-bot`](https://python-telegram-bot.org/) 22.x (async, with JobQueue) |
| HTTP | `requests` |
| Realtime | `websockets` (Binance miniTicker stream) |
| Crypto data | Binance public REST + WebSocket |
| Forex data | Yahoo Finance (realtime) + Frankfurter (ECB fallback) |
| Config | `python-dotenv` |

---

## 📁 Project Structure

```
trade-alert-bot/
├── main.py                 # Entry point — wires stores, realtime, and jobs
├── bot/
│   ├── __init__.py
│   ├── handlers.py         # Telegram command & message handlers
│   ├── alerts.py           # Alert model (price + percent) & store
│   ├── watchlist.py        # Per-user watchlist store
│   ├── subscribers.py      # Opt-in store for news & liquidation alerts
│   ├── news.py             # Seen-news dedup + digest formatting
│   ├── liquidations.py     # Liquidation routing & message formatting
│   ├── jobs.py             # Background jobs: polling, updates, news, digest
│   ├── summary.py          # Shared watchlist-summary message builder
│   └── util.py             # Shared formatting helpers
├── data/
│   ├── __init__.py
│   ├── fetcher.py          # Crypto (Binance) + forex (Yahoo) fetchers
│   ├── realtime.py         # Binance WebSocket price manager
│   ├── liquidations.py     # Binance WebSocket liquidation watcher
│   ├── news.py             # RSS news aggregator
│   ├── newsfilter.py       # Importance scoring (keywords + watchlist symbols)
│   ├── pricecache.py       # In-memory latest-price cache
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
WATCHLIST_UPDATE_INTERVAL=300 # how often watchlist prices are broadcast
DAILY_SUMMARY_TIME=09:00      # daily digest time, "HH:MM" (blank = off)
CACHE_TTL_SECONDS=30          # freshness window for cached realtime prices
NEWS_DROP_INTERVAL=600        # how often new RSS headlines are pushed
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
| `/alert <SYMBOL> <above\|below> <PRICE>` | Price-level alert | `/alert BTCUSDT above 70000` |
| `/alert <SYMBOL> <up\|down\|change> <N%>` | Percentage-move alert | `/alert BTCUSDT up 5%` |
| `/alerts` | List your active alerts | `/alerts` |
| `/remove <ID>` | Remove an alert by ID | `/remove 3` |
| `/watch <SYMBOL ...>` | Add symbols to your watchlist | `/watch BTCUSDT ETHUSDT EURUSD` |
| `/unwatch <SYMBOL>` | Remove a symbol from your watchlist | `/unwatch BTCUSDT` |
| `/watchlist` | Show your watchlist with live prices | `/watchlist` |
| `/clearwatch` | Empty your watchlist | `/clearwatch` |
| `/summary` | Send a watchlist summary right now | `/summary` |
| `/news` | Latest crypto headlines now | `/news` |
| `/newsauto on\|off` | Turn automatic news drops on/off | `/newsauto on` |
| `/liqalert <USD>` | Alert on liquidations worth ≥ USD | `/liqalert 100000` |
| `/liqalert off` | Stop liquidation alerts | `/liqalert off` |

### Examples

```
/price ETHUSDT          →  ETH/USDT: $1,733.65
/price EURUSD           →  EUR/USD: 1.1469
/alert BTCUSDT below 65000
/alert EURUSD above 1.10
/alert BTCUSDT up 5%            → fires when BTC rises 5% from creation
/watch BTCUSDT ETHUSDT EURUSD   → tracked + streamed (crypto) / polled (forex)
/news                          → latest headlines right now (all sources)
/newsauto on                   → only IMPORTANT headlines auto-dropped from then on
/liqalert 100000               → pinged on any liquidation worth ≥ $100k, live
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
