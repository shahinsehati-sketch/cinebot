# -*- coding: utf-8 -*-
# CineBot – نسخه کامل تک‌فایلی (Render-ready)
# امکانات:
#  - منوی فارسی: فیلم/سریال ایرانی و خارجی، آرشیو 3 روز، جستجو نام، جستجوی گسترده، تماس با من
#  - منابع سریع و جستجوی گسترده (سایت‌های آزاد)
#  - خروجی: نام، سال، کیفیت (حدسی از عنوان)، لینک
#  - اسکرپینگ مقاوم با هدر مرورگر + تایم‌اوت + مدیریت خطا
#  - وب‌سرور /health برای نگه داشتن سرویس در Render
#  - بدون وابستگی قطعی به lxml (از html.parser استفاده می‌شود)

import os, re, time, threading, sqlite3, random
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)

# -------- تنظیمات شما --------
BOT_TOKEN     = "8455314722:AAFAIxnHSboXB1UoQEvDJG2Lb8TpPEad_Ko"
ADMIN_CHAT_ID = "821239377"                # عددی
CONTACT_USER  = "shahin_sehati"            # بدون @
CHECK_INTERVAL_SECONDS = 900               # 15 دقیقه
# ------------------------------

UA = "Mozilla/5.0 (Linux; Android 13; Render) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
HDR = {"User-Agent": UA, "Accept-Language": "fa,en;q=0.9"}
REQ_TIMEOUT = 30

DB_FILE = "cinebot_seen.db"

# منابع سریع (برای دکمه‌های اصلی)
QUICK_SOURCES = [
    ("hexdownload", "https://hexdownload.net/category/movie/", "movie"),
    ("hexdownload", "https://hexdownload.net/category/series/", "series"),
    ("uptvs",       "https://uptvs.com/category/movie", "movie"),
    ("uptvs",       "https://uptvs.com/category/series", "series"),
    ("film2movie",  "https://film2movie.asia/category/فیلم-ایرانی/", "movie"),
    ("film2movie",  "https://film2movie.asia/category/سریال-ایرانی/", "series"),
]

# منابع جستجوی گسترده (همراه با سریع‌ها)
EXTENDED_SOURCES = QUICK_SOURCES + [
    ("digimoviez",  "https://digimoviez.net/", "all"),
    ("my-film",     "https://my-film.in/", "all"),
    ("golchindl",   "https://golchindl.me/", "all"),
    ("bia2movies",  "https://bia2movies.bid/", "all"),
    ("1film",       "https://1film.ir/", "all"),
    ("par30dl",     "https://www.par30dl.com/cat/movie/", "movie"),
    ("par30dl",     "https://www.par30dl.com/cat/series/", "series"),
]

QUALITY_HINTS = ["1080", "720", "480", "2160", "4K", "BluRay", "WEB-DL", "WEBRip", "HDRip", "x265", "HEVC", "Dual", "دوبله", "زیرنویس"]

# ---------- پایگاه داده (ممانعت از ارسال تکراری) ----------
def db_init():
    con = sqlite3.connect(DB_FILE); cur = con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS seen (url TEXT PRIMARY KEY, title TEXT, ts TEXT)")
    con.commit(); con.close()

def db_seen_has(url):
    con = sqlite3.connect(DB_FILE); cur = con.cursor()
    cur.execute("SELECT 1 FROM seen WHERE url=?", (url,))
    ok = cur.fetchone() is not None
    con.close(); return ok

def db_seen_add(url, title):
    con = sqlite3.connect(DB_FILE); cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO seen(url,title,ts) VALUES (?,?,?)", (url, title, datetime.utcnow().isoformat()))
    con.commit(); con.close()

# ---------- کمک‌تابع‌ها ----------
def abs_url(base, href):
    if not href: return ""
    if href.startswith("http://") or href.startswith("https://"): return href
    if href.startswith("//"): return "https:" + href
    if href.startswith("/"):
        m = re.match(r"(https?://[^/]+)", base)
        origin = m.group(1) if m else base.rstrip("/")
        return origin + href
    return base.rstrip("/") + "/" + href.lstrip("/")

def guess_year(*texts):
    for s in texts:
        if not s: continue
        m = re.search(r"(19|20)\d{2}", s)
        if m: return m.group(0)
    return "-"

def guess_quality(*texts):
    bag = []
    for s in texts:
        if not s: continue
        for q in QUALITY_HINTS:
            if q.lower() in s.lower() and q not in bag:
                bag.append(q)
    return ", ".join(bag[:6]) if bag else "-"

def is_fa(title):
    return bool(re.search(r"[\u0600-\u06FF]", title or ""))

def looks_foreign(title):
    return bool(re.search(r"[A-Za-z]", title or ""))

def ok_by_rules(title):
    # ایرانی‌ها همیشه اوکی؛ خارجی‌ها اگر در عنوان اشاره به دوبله/زیرنویس باشد
    if is_fa(title) and not looks_foreign(title):
        return True
    if any(k in (title or "") for k in ["دوبله", "زیرنویس", "Dub", "Sub"]):
        return True
    # اگر انگلیسی خالی بود، احتمالا لینک خبر یا … پس رد
    return not looks_foreign(title)

def format_item(source, title, link, extra=None):
    y = guess_year(title, link)
    q = guess_quality(title, extra or "")
    badge = "📺 سریال" if any(w in (title or "") for w in ["سریال","قسمت","فصل"]) else "🎬 فیلم"
    return (
        f"{badge}\n"
        f"📝 نام: {title}\n"
        f"📅 سال: {y}\n"
        f"🎯 کیفیت: {q}\n"
        f"🔗 {link}\n"
        f"↘️ منبع: {source}"
    )

# ---------- دریافت صفحه ----------
def fetch(url):
    try:
        r = requests.get(url, headers=HDR, timeout=REQ_TIMEOUT)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print("fetch error:", url, e)
        return ""

# ---------- استخراج عمومی ----------
def extract_generic(url, limit=60):
    html = fetch(url)
    if not html: return []
    soup = BeautifulSoup(html, "html.parser")
    items = []

    # لینک‌های پرتکرار با عنوان
    for a in soup.find_all("a", href=True, limit=600):
        text = a.get_text(separator=" ", strip=True)
        href = a["href"]
        if not text or len(text) < 2: continue
        # فیلتر لینک‌های ناوبری/بی‌ربط
        if any(bad in href for bad in ["#","javascript:","/tag/","/page/","/category/","/author/"]): 
            continue
        full = abs_url(url, href)
        # یک حداقل: متن باید شبیه عنوان محتوا باشد (فارسی یا شامل year/quality)
        if is_fa(text) or re.search(r"(19|20)\d{2}", text) or any(q.lower() in text.lower() for q in QUALITY_HINTS):
            items.append((text, full))

    # یکتا و کوتاه
    uniq, seen = [], set()
    for t, l in items:
        if (t, l) in seen: continue
        seen.add((t,l)); uniq.append((t,l))
        if len(uniq) >= limit: break
    return uniq

# ---------- استخراج ویژه چند سایت ----------
def extract_hexdownload(url):
    html = fetch(url); 
    if not html: return []
    soup = BeautifulSoup(html, "html.parser")
    out = []
    # کارت‌ها
    for art in soup.select("article, div.post, div.grid-item")[:80]:
        a = art.find("a", href=True)
        if not a: continue
        title = a.get("title") or a.get_text(strip=True)
        link  = abs_url(url, a["href"])
        if title: out.append((title, link))
    if not out:
        out = extract_generic(url, 40)
    return out

def extract_uptvs(url):
    html = fetch(url)
    if not html: return []
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for art in soup.select("article.post, div.post")[:80]:
        a = art.find("a", href=True)
        if not a: continue
        title = a.get("title") or a.get_text(strip=True)
        link  = abs_url(url, a["href"])
        if title: out.append((title, link))
    if not out:
        out = extract_generic(url, 40)
    return out

def extract_film2movie(url):
    html = fetch(url)
    if not html: return []
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for art in soup.select("article, div.post")[:80]:
        a = art.find("a", href=True)
        if not a: continue
        title = a.get("title") or a.get_text(strip=True)
        link  = abs_url(url, a["href"])
        if title: out.append((title, link))
    if not out:
        out = extract_generic(url, 40)
    return out

SPECIAL_EXTRACTORS = {
    "hexdownload": extract_hexdownload,
    "uptvs": extract_uptvs,
    "film2movie": extract_film2movie,
}

def extract_from_source(src_name, url):
    fn = SPECIAL_EXTRACTORS.get(src_name, None)
    try:
        pairs = fn(url) if fn else extract_generic(url, 50)
    except Exception as e:
        print("extractor error:", src_name, url, e)
        pairs = []
    # فیلتر قواعد
    clean = []
    seen = set()
    for title, link in pairs:
        if not link or not title: continue
        if (title, link) in seen: continue
        seen.add((title, link))
        if ok_by_rules(title):
            clean.append((title, link))
    return clean[:20]

# ---------- گردآوری ----------
def collect_quick(kind=None):
    bag = []
    for (name, url, k) in QUICK_SOURCES:
        if kind and k != kind: 
            continue
        bag.extend([(name,)+x for x in extract_from_source(name, url)])
    # یکتا بر اساس لینک
    uniq, seen = [], set()
    random.shuffle(bag)
    for s, t, l in bag:
        if l in seen: continue
        seen.add(l); uniq.append((s,t,l))
        if len(uniq) >= 30: break
    return uniq

def collect_extended(query=None):
    bag = []
    for (name, url, _k) in EXTENDED_SOURCES:
        pairs = extract_from_source(name, url)
        if query:
            q = query.strip().lower()
            pairs = [(t,l) for (t,l) in pairs if q in t.lower()]
        bag.extend([(name,)+x for x in pairs])
        time.sleep(0.2)
    uniq, seen = [], set()
    for s, t, l in bag:
        if l in seen: continue
        seen.add(l); uniq.append((s,t,l))
        if len(uniq) >= 40: break
    return uniq

def collect_last_days(days=3):
    # چون تاریخ دقیق همیشه در HTML نیست، به‌جای تاریخ، از «آخرین آیتم‌های صفحه» استفاده می‌کنیم
    # و فرض می‌گیریم بالای لیست جدیدتره. جمعاً حدود 15-20 آیتم از هر منبع.
    bag = []
    for (name, url, _k) in QUICK_SOURCES:
        pairs = extract_from_source(name, url)[:15]
        bag.extend([(name,)+x for x in pairs])
    uniq, seen = [], set()
    for s, t, l in bag:
        if l in seen: continue
        seen.add(l); uniq.append((s,t,l))
    return uniq[:60]

# ---------- تلگرام UI ----------
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🎬 فیلم ایرانی"), KeyboardButton("📺 سریال ایرانی")],
        [KeyboardButton("🌍 فیلم خارجی"), KeyboardButton("🌍 سریال خارجی")],
        [KeyboardButton("📅 آرشیو ۳ روز"), KeyboardButton("🔍 جستجوی نام")],
        [KeyboardButton("🔎 جستجوی گسترده"), KeyboardButton("📩 تماس با من")],
    ],
    resize_keyboard=True
)

CONTACT_INLINE = InlineKeyboardMarkup([
    [InlineKeyboardButton("ارتباط در تلگرام", url=f"https://t.me/{CONTACT_USER}")]
])

async def send_menu(chat_id, context: ContextTypes.DEFAULT_TYPE, text="یکی از گزینه‌ها رو انتخاب کن:"):
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=MAIN_KEYBOARD)

def send_chunked(context, chat_id, items, prefix=None):
    # ارسال نتایج در چند پیام کوتاه تا محدودیت تلگرام رعایت شود
    count = 0
    block = []
    for (src, title, link) in items:
        msg = format_item(src, title, link)
        block.append(msg); count += 1
        if len("\n\n".join(block)) > 3500 or count % 6 == 0:
            context.bot.send_message(chat_id=chat_id, text=(prefix+"\n" if prefix else "") + "\n\n".join(block))
            block = []
            time.sleep(0.2)
    if block:
        context.bot.send_message(chat_id=chat_id, text=(prefix+"\n" if prefix else "") + "\n\n".join(block))

# ---------- هندلرها ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ ربات فعاله.", reply_markup=MAIN_KEYBOARD)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("از منوی پایین انتخاب کن یا /start رو بزن.", reply_markup=MAIN_KEYBOARD)

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    if text == "📩 تماس با من":
        await context.bot.send_message(chat_id=chat_id, text="برای ارتباط:", reply_markup=CONTACT_INLINE)
        return

    if text == "🎬 فیلم ایرانی":
        await update.message.reply_text("⏳ در حال دریافت فیلم‌های ایرانی جدید از منابع سریع ...")
        items = collect_quick(kind="movie")
        items = [i for i in items if is_fa(i[1])] or items  # ترجیح عنوان فارسی
        if not items:
            await update.message.reply_text("نتیجه‌ای پیدا نشد.")
        else:
            send_chunked(context, chat_id, items[:20], "🎬 فیلم‌های ایرانی جدید:")

    elif text == "📺 سریال ایرانی":
        await update.message.reply_text("⏳ در حال دریافت سریال‌های ایرانی جدید ...")
        items = collect_quick(kind="series")
        items = [i for i in items if is_fa(i[1])] or items
        if not items:
            await update.message.reply_text("نتیجه‌ای پیدا نشد.")
        else:
            send_chunked(context, chat_id, items[:20], "📺 سریال‌های ایرانی جدید:")

    elif text == "🌍 فیلم خارجی":
        await update.message.reply_text("⏳ در حال دریافت فیلم‌های خارجی (با دوبله/زیرنویس) ...")
        items = collect_quick(kind="movie")
        # خارجی‌هایی که اشاره به دوبله/زیرنویس دارند
        items = [i for i in items if any(k in i[1] or k in i[2] for k in ["دوبله","زیرنویس","Dub","Sub","Dual"])]
        if not items:
            await update.message.reply_text("نتیجه‌ای پیدا نشد.")
        else:
            send_chunked(context, chat_id, items[:20], "🌍 فیلم‌های خارجی (Dub/Sub):")

    elif text == "🌍 سریال خارجی":
        await update.message.reply_text("⏳ در حال دریافت سریال‌های خارجی (با دوبله/زیرنویس) ...")
        items = collect_quick(kind="series")
        items = [i for i in items if any(k in i[1] or k in i[2] for k in ["دوبله","زیرنویس","Dub","Sub","Dual","قسمت","فصل"])]
        if not items:
            await update.message.reply_text("نتیجه‌ای پیدا نشد.")
        else:
            send_chunked(context, chat_id, items[:20], "🌍 سریال‌های خارجی (Dub/Sub):")

    elif text == "📅 آرشیو ۳ روز":
        await update.message.reply_text("⏳ در حال گردآوری آرشیو سه روز اخیر (سریع) ...")
        items = collect_last_days(3)
        if not items:
            await update.message.reply_text("چیزی پیدا نشد.")
        else:
            send_chunked(context, chat_id, items[:30], "🗂 آرشیو ۳ روز گذشته:")

    elif text == "🔍 جستجوی نام":
        await update.message.reply_text("نام فیلم/سریال رو بفرست (مثلاً: قورباغه یا Oppenheimer).")

    elif text == "🔎 جستجوی گسترده":
        await update.message.reply_text("نام رو بفرست تا در تمام منابع جستجو کنم.")
        # پرچم مود گسترده
        context.user_data["wide_search"] = True

    else:
        # اگر کاربر نام فرستاد:
        q = text.strip()
        if len(q) >= 2:
            await update.message.reply_text("⏳ در حال جستجو ...")
            wide = context.user_data.pop("wide_search", False)
            items = collect_extended(q) if wide else [
                (s,t,l) for (s,t,l) in collect_quick() if q.lower() in t.lower()
            ]
            if not items:
                await update.message.reply_text("نتیجه‌ای پیدا نشد.")
            else:
                send_chunked(context, chat_id, items[:25], "🔎 نتایج جستجو:")
        else:
            await update.message.reply_text("برای جستجو، حداقل دو کاراکتر بفرست.", reply_markup=MAIN_KEYBOARD)

# ---------- زمان‌بندی خودکار ----------
def scheduler_loop():
    while True:
        try:
            # بررسی منابع سریع و ارسال موارد جدید (فقط لینک‌های جدید)
            items = collect_quick()
            sent = 0
            for (src, title, link) in items:
                if db_seen_has(link): continue
                if not ok_by_rules(title): continue
                msg = format_item(src, title, link)
                try:
                    requests.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                        data={"chat_id": ADMIN_CHAT_ID, "text": msg}, timeout=15
                    )
                    db_seen_add(link, title); sent += 1
                except Exception as e:
                    print("send error:", e)
                time.sleep(0.2)
            if sent == 0:
                print("scheduler: nothing new")
        except Exception as e:
            print("scheduler error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)

# ---------- Flask keep-alive ----------
flask_app = Flask(__name__)

@flask_app.route("/")
def root():
    return "CineBot is running."

@flask_app.route("/health")
def health():
    return jsonify(ok=True, time=datetime.utcnow().isoformat())

def run_flask():
    port = int(os.environ.get("PORT", "10000"))
    flask_app.run(host="0.0.0.0", port=port)

# ---------- Main ----------
def main():
    db_init()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # وب‌سرور و زمان‌بند در ترد جدا
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=scheduler_loop, daemon=True).start()

    print("✅ CineBot ready. Send /start in Telegram.")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
