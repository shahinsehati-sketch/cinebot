import logging
import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackContext, Filters

# ------------------ تنظیمات ------------------
TOKEN = "8153319362:AAGgeAOZyP2VgAdqvjyvvIkgGZBsJtTQOTs"

SITES = {
    "دوستی‌ها": "https://www.doostihaa.com/",
    "UPTV": "https://www.uptvs.com/",
    "HexDownload": "https://hexdownload.co/category/movie/",
    "DigiMovie": "https://digimovie.vip/movies/",
}

# ------------------ لاگ ------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------ شروع ------------------
def start(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [InlineKeyboardButton("🆕 جدیدترین‌ها", callback_data="latest")],
        [InlineKeyboardButton("📩 تماس با ادمین", url="https://t.me/shahin_sehati")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("سلام! 🎥\nبه ربات فیلم خوش اومدی.", reply_markup=reply_markup)

# ------------------ اسکرپ از سایت ------------------
def scrape_latest():
    results = []
    for site, url in SITES.items():
        try:
            r = requests.get(url, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            # گرفتن چند تا عنوان اول
            titles = [a.text.strip() for a in soup.find_all("a") if a.text and len(a.text) > 5][:5]
            for t in titles:
                results.append(f"{site}: {t}")
        except Exception as e:
            results.append(f"{site}: خطا در دریافت اطلاعات ❌")
    return results

def latest(update: Update, context: CallbackContext):
    movies = scrape_latest()
    if not movies:
        update.message.reply_text("❌ چیزی پیدا نشد.")
        return
    msg = "📢 آخرین فیلم‌ها:\n\n" + "\n".join(movies)
    update.message.reply_text(msg)

# ------------------ جستجو ------------------
def search(update: Update, context: CallbackContext):
    query = update.message.text.strip()
    results = []
    for site, url in SITES.items():
        try:
            r = requests.get(url, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            matches = [a.text.strip() for a in soup.find_all("a") if query.lower() in a.text.lower()]
            if matches:
                results.append(f"🔎 {site}: " + ", ".join(matches[:3]))
        except:
            pass
    if results:
        update.message.reply_text("\n".join(results))
    else:
        update.message.reply_text("❌ نتیجه‌ای پیدا نشد.")

# ------------------ اصلی ------------------
def main():
    updater = Updater(TOKEN)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("latest", latest))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, search))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()        
