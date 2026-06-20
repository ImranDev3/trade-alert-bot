# Contributing to trade-alert-bot

Thanks for your interest in improving this bot! 🎉 This is a small project, so
the workflow is intentionally lightweight.

## 🐛 Reporting bugs

Open an issue with:

1. A short, descriptive title
2. What you did (commands / steps to reproduce)
3. What you expected
4. What actually happened (paste the bot's reply or the log line)

## ✨ Suggesting features

Open an issue and describe the use case before writing code — a quick
discussion up front saves rework later.

## 🛠️ Development setup

```bash
git clone https://github.com/ImranDev3/trade-alert-bot.git
cd trade-alert-bot

python -m venv venv
# Windows:
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env      # add your TELEGRAM_BOT_TOKEN
```

## 📋 Code style

- **Python 3.11+**, type hints encouraged (`from __future__ import annotations`).
- Keep functions small and focused; one responsibility per module.
- Use `logging` (already configured in `main.py`), not `print`.
- Never hard-code secrets — everything sensitive comes from `.env`.

## 🧪 Before opening a PR

1. Make sure the project still imports cleanly:
   ```bash
   python -m py_compile config.py bot/*.py data/*.py main.py
   ```
2. Run the bot locally and exercise the affected command(s).
3. Commit with a clear, imperative message, e.g.
   `Add /stats command for alert summary`.
4. Keep PRs focused — one feature or fix per PR.

## 📤 Pull request checklist

- [ ] Branch is up to date with `main`
- [ ] No secrets or `.env` files committed
- [ ] `README.md` updated if the user-facing behaviour changed
- [ ] Commit messages are descriptive

Happy hacking! 🚀
