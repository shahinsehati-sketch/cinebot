# -*- coding: utf-8 -*-
# CineBot – نسخه تک‌فایلی مناسب Render (Polling + وب‌سرور سلامت)
# امکانات:
# - منوی دکمه‌ای فارسی
# - جدیدترین‌ها (از چند منبع فارسی)
# - آرشیو ۳ روز گذشته
# - جستجو بر اساس نام و سال ساخت
# - دکمه تماس با من (آیدی تلگرام)
# - پایدار با مدیریت خطا + وب‌سرور /health برای نگه‌داری سرویس

import os, re, time, threading, sqlite3, requests
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
from flask import Flask, jsonify
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ====== تنظیمات شما ======
BOT_TOKEN     = "8455314722:AAFAIxnHSboXB1UoQEvDJG2Lb8TpPEad_Ko"
ADMIN_CHAT_ID = "821239377"               # آیدی عددی شما
CONTACT_AT    = "shahin_sehati"           # بدون @ هم میشه
CHECK_INTERVAL_SECONDS = 900              # هر ۱۵ دقیقه یک‌بار بررسی خودکار
# ==========================

UA          = "Mozilla/5.0 (Linux; Android 13; Render) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
HDR         = {"User-Agent": UA}
REQ_TIMEOUT = 40
DB_FILE     = "cinebot.db"

# منابع (صفحات عمومی که «لیست جدیدها» دارند؛ ممکنه بعضی‌ها JS داشته باشن—کد fallback دارد)
SOURCES = [
    ("🎬 Filimo",       "https://www.filimo.com/newest"),
    ("🎬 Namava سریال", "https://www.namava.ir/series"),
    ("🎬 Namava فیلم",  "https://www.namava.ir/movies"),
    ("🎬 Telewebion",   "https://www.telewebion.com/new"),
]

FA_DUBSUB = ["دوبله", "دوبله فارسی", "زیرنویس", "زیرنویس فارسی", "Dubbed", "Subtitle", "Sub", "زیر نویس"]

# ---------- DB ----------
def db_init():
    con = sqlite3.connect(DB_FILE); cur = con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS subscribers (chat_id TEXT PRIMARY KEY)")
    cur.execute("CREATE TABLE IF NOT EXISTS seen (url TEXT PRIMARY KEY, title TEXT, source TEXT, ts TEXT)")
    con.commit(); con.close()

def db_add_sub(chat_id):
    con = sqlite3.connect(DB_FILE); cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO subscribers(chat_id) VALUES (?)", (str(chat_id),))
    con.commit(); con.close()

def db_remove_sub(chat_id):
    con = sqlite3.connect(DB_FILE); cur = con.cursor()
    cur.execute("DELETE FROM subscribers WHERE chat_id=?", (str(chat_id),))
    con.commit(); con.close()

def db_get_subs():
    con = sqlite3.connect(DB_FILE); cur = con.cursor()
    cur.execute("SELECT chat_id FROM subscribers")
    rows = [r[0] for r in cur.fetchall()]
    con.close(); return rows

def db_seen_has(url):
    con = sqlite3.connect(DB_FILE); cur = con.cursor()
    cur.execute("SELECT 1 FROM seen WHERE url=?", (url,))
    ok = cur.fetchone() is not None
    con.close(); return ok

def db_seen_add(url, title, source):
    con = sqlite3.connect(DB_FILE); cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO seen(url, title, source, ts) VALUES (?,?,?,?)",
                (url, title, source, datetime.utcnow().isoformat()))
    con.commit(); con.close()

def db_stats():
    con = sqlite3.connect(DB_FILE); cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM subscribers"); subs = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM seen"); seen = cur.fetchone()[0]
    con.close(); return subs, seen

# ---------- Helpers ----------
def abs_url(base_url, href):
    if not href: return ""
    if href.startswith("http://") or href.startswith("https://"): return href
    if href.startswith("//"): return "https:" + href
    if href.startswith("/"):
        import re as _re
        m = _re.match(r"(https?://[^/]+)", base_url)
        origin = m.group(1) if m else base_url.rstrip("/")
        return origin + href
    return base_url.rstrip("/") + "/" + href.lstrip("/")

ISO_PATS = ["%Y-%m-%dT%H:%M:%S%z","%Y-%m-%dT%H:%M:%S.%f%z","%Y-%m-%dT%H:%M:%S","%Y-%m-%d","%Y/%m/%d"]
def parse_date_like(s):
    if not s: return None
    s = s.strip()
    if s.endswith("Z"): s = s[:-1] + "+00:00"
    for p in ISO_PATS:
        try:
            dt = datetime.strptime(s, p)
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except: pass
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        try: return datetime(y, mo, d, tzinfo=timezone.utc)
        except: return None
    return None

def has_persian_dubsub(title):
    low = (title or "").lower()
    return any(kw.lower() in low for kw in FA_DUBSUB)

def is_latin_title(title):
    return bool(re.search(r"[A-Za-z]", title or ""))

def should_send_by_rules(title):
    # عنوان‌های فارسی یا عنوان‌هایی که صراحتاً دوبله/زیرنویس دارند ⇒ ارسال
    if not title: return False
    if has_persian_dubsub(title): return True
    if is_latin_title(title):     return False  # خارجی بدون dub/sub → رد
    return True                   # ایرانی/عمومی

def guess_year(title, link=None, dt=None):
    if dt: return dt.year
    for s in [title or "", link or ""]:
        m = re.search(r"(19|20)\d{2}", s)
        if m: return int(m.group(0))
    return None

def classify_type(title):
    if any(k in (title or "") for k in ["سریال","قسمت","فصل"]): return "series"
    if any(k in (title or "") for k in ["فیلم","سینمایی"]):     return "movie"
    return "title"

def format_msg(source_name, title, link, dt):
    ttype = classify_type(title)
    label = "📺 سریال" if ttype=="series" else ("🎬 فیلم" if ttype=="movie" else "🎞 عنوان")
    badge = "🌍 دوبله/زیرنویس" if has_persian_dubsub(title) else "🇮🇷 ایرانی/عمومی"
    year  = guess_year(title, link, dt) or "-"
    return (
        f"{label} | {badge}\n"
        f"{title}\n"
        f"سال ساخت: {year}\n"
        f"منبع: {source_name}\n"
        f"{link}\n"
        f"⏱ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )

# ---------- Scraper ----------
def fetch_page(url):
    return requests.get(url, headers=HDR, timeout=REQ_TIMEOUT)

def extract_items(name, url):
    items = []
    try:
        r = fetch_page(url)
        soup = BeautifulSoup(r.text, "html.parser")

        # ۱) استخراج عمومی از کارت‌ها / آیتم‌ها
        for c in soup.find_all(["article","li","div"], limit=240):
            a = c.find("a", href=True)
            if not a or not a.get_text(strip=True): continue
            title = a.get_text(strip=True)
            link  = abs_url(url, a["href"])

            # تلاش برای پیدا کردن تاریخ
            dt = None
            t = c.find("time")
            if t:
                if t.has_attr("datetime"):
                    dt = parse_date_like(t["datetime"])
                if not dt and t.get_text(strip=True):
                    dt = parse_date_like(t.get_text(strip=True))

            items.append((title, link, dt))

        # ۲) fallback: هدینگ‌ها
        if not items:
            for a in soup.select("h1 a, h2 a, h3 a"):
                if a.get_text(strip=True) and a.has_attr("href"):
                    items.append((a.get_text(strip=True), abs_url(url, a["href"]), None))

        # حذف تکراری
        seen = set(); out = []
        for t, l, d in items:
            k = (t, l)
            if k in seen: continue
            seen.add(k); out.append((t, l, d))
        return out

    except Exception as e:
        print("extract error:", name, url, e)
        return []

def fetch_all_sources():
    out = []
    for (name, url) in SOURCES:
        out.append((name, extract_items(name, url)))
    return out

# ---------- اعلان ----------
def broadcast(msg):
    subs = db_get_subs()
    targets = subs if subs else ([ADMIN_CHAT_ID] if ADMIN_CHAT_ID else [])
    for chat in targets:
        if not chat: continue
        try:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                data={"chat_id": chat, "text": msg},
                timeout=20
            )
        except Exception as e:
            print("Telegram send error:", e)
        time.sleep(0.2)

def check_and_notify():
    any_new = False
    for source_name, items in fetch_all_sources():
        for title, link, dt in items:
            if not link or db_seen_has(link): continue
            if not should_send_by_rules(title): continue
            msg = format_msg(source_name, title, link, dt)
            broadcast(msg)
            db_seen_add(link, title, source_name)
            any_new = True
    if not any_new:
        print("…no new items")

def seed_last_days(days=3):
    # آرشیو ۳ روز گذشته (قابل تغییر با days)
    lookback = datetime.now(timezone.utc) - timedelta(days=days)
    sent = 0
    for source_name, items in fetch_all_sources():
        # اگه تاریخ نبود، حداقل ۱۵ مورد آخر رو می‌گیریم
        recent = [(t,l,d) for (t,l,d) in items if d and d >= lookback] or items[:15]
        # مرتب‌سازی جدید → قدیم
        recent.sort(key=lambda x: (x[2] or datetime.now(timezone.utc)), reverse=True)
        for title, link, dt in recent:
            if db_seen_has(link): continue
            if not should_send_by_rules(title): continue
            msg = format_msg(source_name, title, link, dt)
            broadcast(msg)
            db_seen_add(link, title, source_name)
            sent += 1
            time.sleep(0.15)
    return sent

# ---------- جستجو ----------
def search_by_name(q):
    q_low = (q or "").strip().lower()
    results = []
    for source_name, items in fetch_all_sources():
        for title, link, dt in items:
            if q_low and q_low in (title or "").lower():
                if should_send_by_rules(title):
                    results.append((source_name, title, link, dt))
    # یکتا و محدود
    uniq = []
    seen = set()
    for s, t, l, d in results:
        if l in seen: continue
        seen.add(l); uniq.append((s,t,l,d))
    return uniq[:25]

def search_by_year(y):
    try:
        y = int(y)
    except:
        return []
    results = []
    for source_name, items in fetch_all_sources():
        for title, link, dt in items:
            year = guess_year(title, link, dt)
            if year == y and should_send_by_rules(title):
                results.append((source_name, title, link, dt))
    uniq = []
    seen = set()
    for s, t, l, d in results:
        if l in seen: continue
        seen.add(l); uniq.append((s,t,l,d))
    return uniq[:25]

# ---------- Telegram UI ----------
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🎬 جدیدترین‌ها"), KeyboardButton("🗂 آرشیو سه روز گذشته")],
        [KeyboardButton("🔍 جستجو (نام)"), KeyboardButton("📅 جستجو (سال ساخت)")],
        [KeyboardButton("📩 تماس با من")]
    ],
    resize_keyboard=True
)

CONTACT_INLINE = InlineKeyboardMarkup([
    [InlineKeyboardButton("ارتباط در تلگرام", url=f"https://t.me/{CONTACT_AT.lstrip('@')}")]
])

async def send_menu(chat_id, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=chat_id,
        text="یکی از گزینه‌ها رو انتخاب کن:",
        reply_markup=MAIN_KEYBOARD
    )

# ---------- Command Handlers ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    db_add_sub(chat_id)
    await context.bot.send_message(chat_id=chat_id, text="✅ ربات فعاله. از منوی پایین انتخاب کن.", reply_markup=MAIN_KEYBOARD)

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subs, seen = db_stats()
    await update.message.reply_text(f"ℹ️ وضعیت:\n👥 مشترک‌ها: {subs}\n🔗 عناوین ثبت‌شده: {seen}\n⏱ بازه بررسی: هر ۱۵ دقیقه")

async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ در حال بررسی منابع ...")
    check_and_notify()
    await update.message.reply_text("✅ بررسی تمام شد.")

async def cmd_seed3d(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ ارسال آرشیو ۳ روز گذشته ...")
    c = seed_last_days(3)
    await update.message.reply_text(f"✅ تمام شد. تعداد ارسال: {c}")

async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = " ".join(context.args).strip()
    if not q:
        await update.message.reply_text("مثال: /search قورباغه")
        return
    matches = search_by_name(q)
    if not matches:
        await update.message.reply_text("هیچی پیدا نشد.")
        return
    for s, t, l, d in matches:
        await update.message.reply_text(format_msg(s, t, l, d))
        time.sleep(0.15)

async def cmd_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("مثال: /year 2023")
        return
    y = context.args[0]
    matches = search_by_year(y)
    if not matches:
        await update.message.reply_text("برای این سال چیزی پیدا نشد.")
        return
    for s, t, l, d in matches:
        await update.message.reply_text(format_msg(s, t, l, d))
        time.sleep(0.15)

# ---------- Text Buttons ----------
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    text = (update.message.text or "").strip()

    if text == "🎬 جدیدترین‌ها":
        await update.message.reply_text("⏳ در حال دریافت جدیدترین‌ها ...")
        check_and_notify()
        await update.message.reply_text("✅ ارسال شد (اگر مورد جدیدی بود).")

    elif text == "🗂 آرشیو سه روز گذشته":
        await update.message.reply_text("⏳ در حال ارسال آرشیو ۳ روز گذشته ...")
        c = seed_last_days(3)
        await update.message.reply_text(f"✅ تمام شد. تعداد ارسال: {c}")

    elif text == "🔍 جستجو (نام)":
        await update.message.reply_text("نام فیلم/سریال رو بفرست (مثلاً: قورباغه)")

    elif text == "📅 جستجو (سال ساخت)":
        await update.message.reply_text("سال ساخت رو بفرست (مثلاً: 2022)")

    elif text == "📩 تماس با من":
        await context.bot.send_message(chat_id=chat_id, text="برای ارتباط:", reply_markup=CONTACT_INLINE)

    else:
        # اگر کاربر بعد از انتخاب «جستجو» مستقیم نام/سال فرستاد
        if re.fullmatch(r"\d{4}", text):
            matches = search_by_year(text)
            if not matches:
                await update.message.reply_text("برای این سال چیزی پیدا نشد.")
            else:
                for s, t, l, d in matches:
                    await update.message.reply_text(format_msg(s, t, l, d))
                    time.sleep(0.15)
        else:
            # جستجوی نام به صورت پیش‌فرض
            if len(text) >= 2:
                matches = search_by_name(text)
                if not matches:
                    await update.message.reply_text("نتیجه‌ای پیدا نشد.")
                else:
                    for s, t, l, d in matches:
                        await update.message.reply_text(format_msg(s, t, l, d))
                        time.sleep(0.15)
            else:
                await send_menu(chat_id, context)

# ---------- Scheduler ----------
def scheduler_loop(app: "ApplicationBuilder"):
    # حلقه جدا برای بررسی خودکار
    while True:
        try:
            check_and_notify()
        except Exception as e:
            print("scheduler error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)

# ---------- Flask keep-alive ----------
flask_app = Flask(__name__)

@flask_app.route("/")
def root():
    return "CineBot is alive."

@flask_app.route("/health")
def health():
    subs, seen = db_stats()
    return jsonify(ok=True, subs=subs, seen=seen, time=datetime.now().strftime("%Y-%m-%d %H:%M"))

def run_flask():
    port = int(os.environ.get("PORT", "10000"))
    flask_app.run(host="0.0.0.0", port=port)

# ---------- Main ----------
def main():
    db_init()
    if ADMIN_CHAT_ID:
        db_add_sub(ADMIN_CHAT_ID)

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("seed3d", cmd_seed3d))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("year", cmd_year))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # Flask برای سلامت سرویس
    threading.Thread(target=run_flask, daemon=True).start()
    # Scheduler خودکار
    threading.Thread(target=scheduler_loop, args=(app,), daemon=True).start()

    print("✅ CineBot running (Render). Use /start in Telegram.")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()# cinebot
