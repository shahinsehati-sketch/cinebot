#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import requests
from telegram import ParseMode
from telegram.ext import Updater, CommandHandler
import time

# ---------------- تنظیمات ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8153319362:AAGgeAOZyP2VgAdqvjyvvIkgGZBsJtTQOTs"
DEFAULT_CHAT_ID = "821239377"
PUSH_EVERY_MIN = 5
MANUAL_TOMAN_RATE = 0

COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"
FX_URL = "https://api.exchangerate.host/latest?base=USD&symbols=IRR"
HEADERS = {"User-Agent": "CryptoWatcherBot/1.0"}


# ---------------- گرفتن داده‌ها ----------------
def fetch_top():
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 15,
        "page": 1,
        "price_change_percentage": "24h",
    }
    r = requests.get(COINGECKO_URL, params=params, timeout=20, headers=HEADERS)
    r.raise_for_status()
    data = r.json()
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


def fetch_usd_to_toman():
    if MANUAL_TOMAN_RATE > 0:
        return MANUAL_TOMAN_RATE
    r = requests.get(FX_URL, timeout=15, headers=HEADERS)
    r.raise_for_status()
    js = r.json() or {}
    irr = float(js.get("rates", {}).get("IRR") or 0)
    if irr <= 0:
        raise RuntimeError("Invalid IRR rate")
    return irr / 10.0


# ---------------- فرمت‌بندی ----------------
def fmt_num(n, digits=2):
    return f"{n:,.{digits}f}".replace(",", "_").replace("_", ",")


def render_message(rows, usd_to_toman):
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


# ---------------- هندلرها ----------------
def now(update, context):
    try:
        rows = fetch_top()
        usd_to_toman = fetch_usd_to_toman()
        text = render_message(rows, usd_to_toman)
        update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        logger.exception("/now failed")
        update.message.reply_text(f"خطا: {e}")


def periodic_job(context):
    try:
        rows = fetch_top()
        usd_to_toman = fetch_usd_to_toman()
        text = render_message(rows, usd_to_toman)
        context.bot.send_message(
            chat_id=DEFAULT_CHAT_ID,
            text=text,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        logger.exception("push failed")


# ---------------- اجرای اصلی ----------------
def main():
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("now", now))

    # کار زمان‌بندی شده
    jq = updater.job_queue
    jq.run_repeating(periodic_job, interval=PUSH_EVERY_MIN * 60, first=5)

    logger.info("Bot is running…")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
