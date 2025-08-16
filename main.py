import asyncio
import requests
from aiogram import Bot, Dispatcher
from datetime import datetime, timedelta, timezone

# اطلاعات ربات
TOKEN = "8153319362:AAGgeAOZyP2VgAdqvjyvvIkgGZBsJtTQOTs"
CHAT_ID = 821239377

bot = Bot(token=TOKEN)
dp = Dispatcher()

# گرفتن نرخ دلار (USDT) به تومان
def get_usd_to_irr():
    # اول نوبیتکس
    try:
        url = "https://api.nobitex.ir/market/stats"
        response = requests.get(url, timeout=10).json()
        usdt_price = float(response["global"]["binance"]["USDTIRT"]["latest"])
        return usdt_price
    except Exception as e:
        print("❌ Nobitex در دسترس نیست:", e)

    # fallback: ارزدیجیتال
    try:
        url = "https://api.arzdigital.com/public/v1/price/USDT"
        response = requests.get(url, timeout=10).json()
        usdt_price = float(response["data"]["price"])
        return usdt_price
    except Exception as e:
        print("❌ Arzdigital در دسترس نیست:", e)

    # fallback نهایی
    return 60000  

# گرفتن اطلاعات ۱۵ ارز برتر
def fetch_crypto_data():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {"vs_currency": "usd", "order": "market_cap_desc", "per_page": 15, "page": 1}
    response = requests.get(url, params=params, timeout=10)
    data = response.json()

    usd_to_irr = get_usd_to_irr()

    # زمان به وقت ایران
    iran_time = datetime.now(timezone.utc) + timedelta(hours=3, minutes=30)
    time_str = iran_time.strftime("%Y-%m-%d ⏰ %H:%M")

    message = f"💹 قیمت ۱۵ ارز برتر\n\n"
    message += f"💵 نرخ لحظه‌ای دلار (تتر): {usd_to_irr:,.0f} تومان\n"
    message += f"📅 آخرین بروزرسانی: {time_str}\n\n"

    for coin in data:
        usd_price = coin['current_price']
        irr_price = usd_price * usd_to_irr
        change = coin['price_change_percentage_24h']
        message += f"🔸 {coin['name']} ({coin['symbol'].upper()})\n"
        message += f"💵 {usd_price:,.2f} دلار | 🇮🇷 {irr_price:,.0f} تومان\n"
        message += f"📉 تغییرات ۲۴ساعت: {change:.2f}%\n\n"

    return message

# ارسال پیام هر ۵ دقیقه
async def send_updates():
    while True:
        try:
            text = fetch_crypto_data()
            await bot.send_message(chat_id=CHAT_ID, text=text)
        except Exception as e:
            print("خطا در ارسال:", e)
        await asyncio.sleep(300)

async def main():
    asyncio.create_task(send_updates())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
