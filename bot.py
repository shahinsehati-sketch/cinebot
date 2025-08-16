import logging
from flask import Flask, request
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
import requests
from bs4 import BeautifulSoup

# توکن جدید
TOKEN = "8153319362:AAGgeAOZyP2VgAdqvjyvvIkgGZBsJtTQOTs"
APP_NAME = "cinebot"  # اسم اپت روی Render

# ربات
bot = telegram.Bot(token=TOKEN)

app = Flask(__name__)

# لاگ
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    level=logging.INFO)

# هندلر دیسپچر
dispatcher = Dispatcher(bot, None, workers=0)


# /start
def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🎬 فیلم‌های جدید", callback_data="latest_movies")],
        [InlineKeyboardButton("📺 سریال‌های جدید", callback_data="latest_series")],
        [InlineKeyboardButton("🔎 جستجو", callback_data="search")],
        [InlineKeyboardButton("🗂 آرشیو (۳ روز اخیر)", callback_data="archive")],
        [InlineKeyboardButton("📩 تماس با من", url="https://t.me/shahin_sehati")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("سلام! 🎥 به ربات فیلم خوش اومدی.\nیکی از گزینه‌های زیر رو انتخاب کن:", reply_markup=reply_markup)


def button(update, context):
    query = update.callback_query
    data = query.data

    if data == "latest_movies":
        query.edit_message_text("🔄 در حال دریافت جدیدترین فیلم‌ها...")
        # اینجا باید scraping یا API اضافه بشه
        query.message.reply_text("🎬 فیلم جدید: نمونه ۱\n🎬 فیلم جدید: نمونه ۲")

    elif data == "latest_series":
        query.edit_message_text("🔄 در حال دریافت جدیدترین سریال‌ها...")
        query.message.reply_text("📺 سریال جدید: نمونه A\n📺 سریال جدید: نمونه B")

    elif data == "archive":
        query.edit_message_text("🗂 آرشیو سه روز اخیر:")
        query.message.reply_text("🎬 فیلم روز قبل: X\n📺 سریال روز قبل: Y")

    elif data == "search":
        query.edit_message_text("🔎 لطفا اسم فیلم یا سریال مورد نظر رو بفرستید.")


def search_handler(update, context):
    text = update.message.text
    # اینجا باید جستجو در سایت‌ها انجام بشه
    update.message.reply_text(f"🔍 نتیجه جستجو برای '{text}':\nمتأسفانه هنوز منبع جستجو کامل نشده.")


# ثبت دستورات
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CallbackQueryHandler(button))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, search_handler))


# وبهوک
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = telegram.Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"


@app.route("/")
def index():
    return "CineBot running!"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
