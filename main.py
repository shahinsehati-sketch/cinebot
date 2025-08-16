#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CryptoWatcherBot — نسخه نهایی سازگار
-----------------------------------
- هر ۵ دقیقه
- ۱۵ ارز برتر
- توکن و chat_id داخل کد
- سازگار با python-telegram-bot نسخه‌های جدید (۲۱.x) و قدیمی‌تر (۱۳.x)
"""
from __future__ import annotations
import asyncio
import logging
from typing import Dict, List

import requests
from telegram.constants import ParseMode
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

# --------------- Config & Logging ---------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("CryptoWatcherBot")

# این مقادیر ثابت شده‌اند
BOT_TOKEN = "8153319362:AAGgeAOZyP2VgAdqvjyvvIkgGZBsJtTQOTs"
DEFAULT_CHAT_ID = "821239377"
PUSH_EVERY_MIN = 5
MANUAL_TOMAN_RATE = 0

# --------------- Data Fetchers ---------------
COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"
FX_URL = "https://api.exchangerate.host/latest?base=USD&symbols=IRR"
HEADERS = {"User-Agent": "CryptoWatcherBot/1.0"}


def fetch_top() -> List[Dict]:
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 15,
        "page": 1,
        "price_change_percentage": "24h",
        "locale": "en",
    }
    r = requests.get(COINGECKO_URL, params=params, timeout=20, headers=HEADERS)
    r.raise_for_status()
    data: List[Dict] = r.json()
    neat = []
    for d in data:
        neat.append(
            {
                "symbol": (d.get("symbol") or "").upper(),
                "name": d.get("name") or "",
                "price_usd": float(d.get("current_price") or 0.0),
                "change_24h": float(d.get("price_change_percentage_24h") or 0.0),
            }
        )
    return neat


def fetch_usd_to_toman() -> float:
    if MANUAL_TOMAN_RATE > 0:
        return MANUAL_TOMAN_RATE
    r = requests.get(FX_URL, timeout=15, headers=HEADERS)
    r.raise_for_status()
    js = r.json() or {}
    irr = float(js.get("rates", {}).get("IRR") or 0)
    if irr <= 0:
        raise RuntimeError("Invalid IRR rate")
    return irr / 10.0


# --------------- Formatting ---------------
def fmt_num(n: float, digits: int = 2) -> str:
    return f"{n:,.{digits}f}".replace(",", "_").replace("_", ",")


def render_message(rows: List[Dict], usd_to_toman: float) -> str:
    lines = []
    lines.append("Top 15 by Market Cap — Every 5 minutes\n")
    lines.append(f"USD→Toman ≈ {fmt_num(usd_to_toman, 0)} تومان\n")
    lines.append("```\n")
    lines.append(f"{'#':>2}  {'Coin':8}  {'USD':>14}  {'Toman':>16}  {'24h%':>7}")
    lines.append("-" * 56)
    for i, r in enumerate(rows, 1):
        usd = r["price_usd"]
        toman = usd * usd_to_toman
        pct = r["change_24h"]
        coin = (r["symbol"] or "?")[:8].ljust(8)
        lines.append(
            f"{i:>2}  {coin}  {fmt_num(usd, 2):>14}  {fmt_num(toman, 0):>16}  {pct:+6.2f}"
        )
    lines.append("```")
    lines.append("\nData: CoinGecko • FX: exchangerate.host")
    return "\n".join(lines)


# --------------- Bot Handlers ---------------
async def now(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        rows = fetch_top()
        usd_to_toman = fetch_usd_to_toman()
        text = render_message(rows, usd_to_toman)
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        logger.exception("/now failed")
        await update.message.reply_text(f"خطا: {e}")


async def _send_once(app: Application, chat_id: int) -> None:
    try:
        rows = fetch_top()
        usd_to_toman = fetch_usd_to_toman()
        text = render_message(rows, usd_to_toman)
        await app.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        logger.exception("push failed")


async def periodic_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    app: Application = context.application
    if DEFAULT_CHAT_ID and DEFAULT_CHAT_ID.isdigit():
        await _send_once(app, int(DEFAULT_CHAT_ID))


async def main() -> None:
    application: Application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("now", now))

    # سازگاری با نسخه‌های مختلف python-telegram-bot
    job_queue = getattr(application, "job_queue", None)
    if job_queue is None:
        try:
            from telegram.ext import JobQueue
            job_queue = JobQueue()
            job_queue.set_application(application)
            job_queue.start()
        except Exception as e:
            logger.error("JobQueue not available: %s", e)
            job_queue = None

    if job_queue:
        job_queue.run_repeating(periodic_job, interval=PUSH_EVERY_MIN * 60, first=5)

    logger.info("Bot is up. Sending to CHAT_ID=%s every %d min", DEFAULT_CHAT_ID or "<none>", PUSH_EVERY_MIN)
    await application.run_polling()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Shutting down…")
