# -*- coding: utf-8 -*-
# CineBot (Legal New Releases Notifier) – Filimo / Namava / Filmnet / SalamCinema / Cinematicket
# Text-only (no image download). Outputs: title + year (+genre if text contains it) + official page link.
# python-telegram-bot v13.x compatible. Flask keep-alive for Render. No lxml dependency.

import os, re, time, threading, random, logging
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# ====== YOUR SETTINGS ======
BOT_TOKEN     = "8153319362:AAGgeAOZyP2VgAdqvjyvvIkgGZBsJtTQOTs"
ADMIN_CHAT_ID = 821239377
CONTACT_USER  = "shahin_sehati"
CHECK_INTERVAL_SECONDS = 900  # every 15 minutes
# ===========================

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
log = logging.getLogger("CineBotLegal")

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
HDR = {"User-Agent": UA, "Accept-Language": "fa,en;q=0.9"}
REQ_TIMEOUT = 25

# ---------- Helpers ----------
def fetch(url):
    try:
        r = requests.get(url, headers=HDR, timeout=REQ_TIMEOUT)
        r.raise_for_status()
        return r.text
    except Exception as e:
        log.warning(f"fetch error: {url} -> {e}")
        return ""

def abs_url(base, href):
    if not href: return ""
    if href.startswith("http"): return href
    if href.startswith("//"): return "https:" + href
    if href.startswith("/"):
        m = re.match(r"(https?://[^/]+)", base)
        origin = m.group(1) if m else base.rstrip("/")
        return origin + href
    return base.rstrip("/") + "/" + href.lstrip("/")

def guess_year(text):
    if not text: return "-"
    m = re.search(r"(19|20)\d{2}", text)
    return m.group(0) if m else "-"

def maybe_genre(text):
    if not text: return "-"
    # very light heuristic
    genres_fa = ["اکشن","ماجراجویی","انیمیشن","کمدی","جنایی","درام","فانتزی","تاریخی","ترسناک","معمایی","عاشقانه","علمی","ورزشی","جنگی","خانوادگی","مستند"]
    found = [g for g in genres_fa if g in text]
    return "، ".join(found) if found else "-"

def split_blocks(lines, max_len=3500, per_msg=6):
    out, buf = [], []
    for i, block in enumerate(lines, 1):
        buf.append(block)
        if len("\n\n".join(buf)) > max_len or (i % per_msg == 0):
            out.append("\n\n".join(buf)); buf = []
    if buf: out.append("\n\n".join(buf))
    return out

def format_item(platform, title, link, extra_txt=""):
    year = guess_year(title + " " + extra_txt)
    genre = maybe_genre(title + " " + extra_txt)
    badge = "📺 سریال" if any(w in title for w in ["سریال","Season","قسمت","فصل"]) else "🎬 فیلم"
    return (
        f"{badge}\n"
        f"📝 نام: {title}\n"
        f"📅 سال: {year}\n"
        f"🎭 ژانر: {genre}\n"
        f"🔗 {link}\n"
        f"↘️ منبع: {platform}"
    )

# ---------- Scrapers (legal & public) ----------
def filimo_latest(limit=30):
    base = "https://www.filimo.com"
    url  = base + "/newest"
    html = fetch(url)
    if not html: return []
    soup = BeautifulSoup(html, "html.parser")
    out = []
    cards = soup.select("a[href^='/m/'], a[href^='/s/'], div a[href*='/m/'], div a[href*='/s/']")
    if not cards: cards = soup.find_all("a", href=True)

    for a in cards:
        href  = a.get("href") or ""
        if not any(p in href for p in ["/m/","/s/"]): continue
        title = (a.get("title") or a.get_text(" ", strip=True) or "").strip()
        if len(title) < 2: continue
        out.append(("فیلیمو", title, abs_url(base, href)))
        if len(out) >= limit: break

    # unique by link
    seen, uniq = set(), []
    for item in out:
        if item[2] in seen: continue
        seen.add(item[2]); uniq.append(item)
    return uniq[:limit]

def namava_latest(limit=30):
    base = "https://www.namava.ir"
    urls = [base + "/movies", base + "/series", base + "/recently-added"]
    out = []
    for url in urls:
        html = fetch(url)
        if not html: continue
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("a[href^='/movie/'], a[href^='/series/'], a[href*='/content/']")
        if not cards: cards = soup.find_all("a", href=True)
        for a in cards:
            href = a.get("href") or ""
            if not any(x in href for x in ["/movie/","/series/","/content/"]): continue
            title = (a.get("title") or a.get_text(" ", strip=True) or "").strip()
            if len(title) < 2: continue
            out.append(("نماوا", title, abs_url(base, href)))
            if len(out) >= limit: break
        if len(out) >= limit: break
    # unique
    seen, uniq = set(), []
    for item in out:
        if item[2] in seen: continue
        seen.add(item[2]); uniq.append(item)
    return uniq[:limit]

def filmnet_latest(limit=30):
    base = "https://filmnet.ir"
    urls = [base + "/movies", base + "/series"]
    out = []
    for url in urls:
        html = fetch(url)
        if not html: continue
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("a[href^='/title/'], a[href^='/movies/'], a[href^='/series/']")
        if not cards: cards = soup.find_all("a", href=True)
        for a in cards:
            href = a.get("href") or ""
            if not any(x in href for x in ["/title/","/movies/","/series/"]): continue
            title = (a.get("title") or a.get_text(" ", strip=True) or "").strip()
            if len(title) < 2: continue
            out.append(("فیلم‌نت", title, abs_url(base, href)))
            if len(out) >= limit: break
        if len(out) >= limit: break
    # unique
    seen, uniq = set(), []
    for item in out:
        if item[2] in seen: continue
        seen.add(item[2]); uniq.append(item)
    return uniq[:limit]

def salamsinema_latest(limit=30):
    # اطلاع‌رسانی فیلم‌ها/خبرهای جدید (بدون دانلود)
    base = "https://www.salamcinama.ir"
    url  = base + "/news"
    html = fetch(url)
    if not html: return []
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href or "/news/" not in href: continue
        title = a.get("title") or a.get_text(" ", strip=True)
        if not title or len(title) < 4: continue
        out.append(("سلام‌سینما", title.strip(), abs_url(base, href)))
        if len(out) >= limit: break
    # unique
    seen, uniq = set(), []
    for item in out:
        if item[2] in seen: continue
        seen.add(item[2]); uniq.append(item)
    return uniq[:limit]

def cinematicket_coming(limit=30):
    base = "https://www.cinematicket.org"
    url  = base + "/movies/comingsoon"
    html = fetch(url)
    if not html:
        # fallback صفحه اصلی
        html = fetch(base)
        if not html: return []
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href or ("movie" not in href and "movies" not in href): continue
        title = a.get("title") or a.get_text(" ", strip=True)
        if not title or len(title) < 2: continue
        out.append(("سینماتیکت", title.strip(), abs_url(base, href)))
        if len(out) >= limit: break
    # unique
    seen, uniq = set(), []
    for item in out:
        if item[2] in seen: continue
        seen.add(item[2]); uniq.append(item)
    return uniq[:limit]

# Aggregators
def latest_movies(limit=30):
    bag = []
    bag += filimo_latest(20)
    bag += namava_latest(20)
    bag += filmnet_latest(20)
    # در منابع بالا فیلم/سریال قاطی می‌آید؛ بعداً با badge مشخص می‌کنیم
    random.shuffle(bag)
    # unique by link
    seen, uniq = set(), []
    for item in bag:
        if item[2] in seen: continue
        seen.add(item[2]); uniq.append(item)
        if len(uniq) >= limit: break
    return uniq

def latest_series(limit=30):
    # همان منابع؛ فیلتر بر اساس کلمات سریالی
    items = latest_movies(80)
    series = []
    for plat, title, link in items:
        if any(w in title for w in ["سریال","قسمت","Season","فصل"]):
            series.append((plat,title,link))
        if len(series) >= limit: break
    return series

def archive_last3days(limit=40):
    # چون تاریخ دقیق در HTML همه‌ی منابع نیست، از آخرین موارد صفحه‌ها استفاده می‌کنیم
    bag = filimo_latest(20) + namava_latest(20) + filmnet_latest(20) + salamsinema_latest(12) + cinematicket_coming(12)
    random.shuffle(bag)
    # unique
    seen, uniq = set(), []
    for item in bag:
        if item[2] in seen: continue
        seen.add(item[2]); uniq.append(item)
        if len(uniq) >= limit: break
    return uniq

def search_all(q, by_year=False, limit=40):
    ql = (q or "").strip().lower()
    bag = filimo_latest(60) + namava_latest(60) + filmnet_latest(60) + salamsinema_latest(40) + cinematicket_coming(40)
    res = []
    for plat, title, link in bag:
        hay = title.lower()
        if by_year:
            y = guess_year(title)
            if y != "-" and ql in y.lower():
                res.append((plat,title,link))
        else:
            if ql in hay:
                res.append((plat,title,link))
        if len(res) >= limit: break
    return res

# ---------- Telegram UI ----------
MAIN_KEYS = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🎥 فیلم‌های جدید"), KeyboardButton("📺 سریال‌های جدید")],
        [KeyboardButton("🔍 جستجو (نام)"), KeyboardButton("📅 جستجو (سال)")],
        [KeyboardButton("🗂 آرشیو ۳ روز اخیر"), KeyboardButton("📩 تماس با من")],
    ],
    resize_keyboard=True
)
CONTACT_INLINE = InlineKeyboardMarkup(
    [[InlineKeyboardButton("ارتباط در تلگرام", url=f"https://t.me/{CONTACT_USER}")]]
)

def cmd_start(update: Update, context: CallbackContext):
    update.message.reply_text("✅ ربات فعاله. از منوی پایین انتخاب کن:", reply_markup=MAIN_KEYS)

def cmd_help(update: Update, context: CallbackContext):
    update.message.reply_text("از دکمه‌ها استفاده کن یا /start رو بزن.", reply_markup=MAIN_KEYS)

def on_text(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    if text == "📩 تماس با من":
        context.bot.send_message(chat_id=chat_id, text="برای ارتباط:", reply_markup=CONTACT_INLINE)
        return

    if text == "🎥 فیلم‌های جدید":
        update.message.reply_text("⏳ در حال دریافت جدیدترین‌ها از منابع رسمی ...")
        items = latest_movies(24)
        if not items:
            update.message.reply_text("❌ نتیجه‌ای پیدا نشد.")
        else:
            blocks = [format_item(*it, "") for it in items]
            for chunk in split_blocks(blocks):
                context.bot.send_message(chat_id=chat_id, text=chunk)
        return

    if text == "📺 سریال‌های جدید":
        update.message.reply_text("⏳ در حال دریافت سریال‌ها ...")
        items = latest_series(24)
        if not items:
            update.message.reply_text("❌ نتیجه‌ای پیدا نشد.")
        else:
            blocks = [format_item(*it, "") for it in items]
            for chunk in split_blocks(blocks):
                context.bot.send_message(chat_id=chat_id, text=chunk)
        return

    if text == "🗂 آرشیو ۳ روز اخیر":
        update.message.reply_text("⏳ در حال گردآوری آرشیو ...")
        items = archive_last3days(40)
        if not items:
            update.message.reply_text("❌ چیزی پیدا نشد.")
        else:
            blocks = [format_item(*it, "") for it in items]
            for chunk in split_blocks(blocks):
                context.bot.send_message(chat_id=chat_id, text=chunk)
        return

    if text == "🔍 جستجو (نام)":
        context.user_data["mode"] = "name"
        update.message.reply_text("نام فیلم/سریال را بفرست (فارسی یا انگلیسی).")
        return

    if text == "📅 جستجو (سال)":
        context.user_data["mode"] = "year"
        update.message.reply_text("سال ساخت را بفرست (مثلاً: 2023).")
        return

    # query handler
    mode = context.user_data.get("mode")
    if mode == "name" and len(text) >= 2:
        update.message.reply_text("⏳ در حال جستجو بر اساس نام ...")
        items = search_all(text, by_year=False, limit=30)
        context.user_data["mode"] = None
        if not items:
            update.message.reply_text("چیزی پیدا نشد.")
        else:
            blocks = [format_item(*it, "") for it in items]
            for chunk in split_blocks(blocks):
                context.bot.send_message(chat_id=chat_id, text=chunk)
        return
    elif mode == "year" and re.fullmatch(r"\d{4}", text or ""):
        update.message.reply_text("⏳ در حال جستجو بر اساس سال ...")
        items = search_all(text, by_year=True, limit=30)
        context.user_data["mode"] = None
        if not items:
            update.message.reply_text("چیزی پیدا نشد.")
        else:
            blocks = [format_item(*it, "") for it in items]
            for chunk in split_blocks(blocks):
                context.bot.send_message(chat_id=chat_id, text=chunk)
        return
    else:
        update.message.reply_text("از منو استفاده کن یا /start رو بزن.", reply_markup=MAIN_KEYS)

def error_handler(update: Update, context: CallbackContext):
    log.warning(f"Update {update} caused error {context.error}")

# ---------- Flask keep-alive (Render) ----------
flask_app = Flask(__name__)

@flask_app.route("/")
def root():
    return "CineBot (legal) is running."

@flask_app.route("/health")
def health():
    return jsonify(ok=True, time=datetime.utcnow().isoformat())

def run_flask():
    port = int(os.environ.get("PORT", "10000"))
    flask_app.run(host="0.0.0.0", port=port)

# ---------- Optional notifier (send to admin) ----------
def scheduler_loop(bot):
    last_sent = set()
    while True:
        try:
            bag = archive_last3days(20)
            new_items = [(p,t,l) for (p,t,l) in bag if l not in last_sent]
            for p,t,l in new_items:
                bot.send_message(chat_id=ADMIN_CHAT_ID, text=format_item(p,t,l))
                last_sent.add(l)
                time.sleep(0.3)
            if not new_items:
                log.info("scheduler: nothing new")
        except Exception as e:
            log.warning(f"scheduler error: {e}")
        time.sleep(CHECK_INTERVAL_SECONDS)

# ---------- Main ----------
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", cmd_start))
    dp.add_handler(CommandHandler("help", cmd_help))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, on_text))
    dp.add_error_handler(error_handler)

    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=scheduler_loop, args=(updater.bot,), daemon=True).start()

    log.info("CineBot (legal) running. Send /start in Telegram.")
    updater.start_polling(drop_pending_updates=True)
    updater.idle()

if __name__ == "__main__":
    main()
