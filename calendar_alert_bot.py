import os
import asyncio
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from telegram import Bot
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# === Настройки из переменных окружения ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
THREAD_ID = os.getenv("MESSAGE_THREAD_ID")  # Можно оставить пустым

bot = Bot(token=BOT_TOKEN)

CHECK_INTERVAL = 60  # интервал проверки (в секундах)
DAILY_ALERT_HOUR = 8  # 08:00 по Киеву

sent_events = set()
reminded_events = set()

# === Получение событий с Investing.com ===
def fetch_events():
    url = "https://www.investing.com/economic-calendar/"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.content, "html.parser")
        rows = soup.select("tr.js-event-item")

        events = []
        for row in rows:
            impact = row.select_one(".sentiment .grayFullBullish")
            if not impact or len(impact.select("i")) < 3:
                continue  # не "красная" новость

            currency = row.get("data-event-currency")
            timestamp = row.get("data-event-datetime")
            title = row.get("data-event-title")

            if not (timestamp and title and currency):
                continue

            dt = datetime.utcfromtimestamp(int(timestamp)) + timedelta(hours=3)  # UTC+3 (Киев)

            events.append({
                "key": f"{currency}_{title}_{dt.isoformat()}",
                "title": title,
                "currency": currency,
                "datetime": dt,
            })

        return events

    except Exception as e:
        print("❌ Ошибка загрузки:", e)
        return []

# === Отправка сообщений ===
async def send_message(text):
    try:
        await bot.send_message(
            chat_id=CHAT_ID,
            text=text,
            parse_mode="HTML",
            message_thread_id=int(THREAD_ID) if THREAD_ID else None
        )
    except Exception as e:
        print("❌ Ошибка отправки сообщения:", e)

# === Ежедневный дайджест ===
async def send_daily_summary(events):
    if not events:
        return

    today = datetime.now().strftime('%d.%m.%Y')
    lines = [f"📅 <b>Красные новости на сегодня ({today}):</b>\n"]

    for e in events:
        if e['datetime'].date() == datetime.now().date():
            lines.append(f"🕒 {e['datetime'].strftime('%H:%M')} — <b>{e['title']}</b> ({e['currency']})")

    if len(lines) > 1:
        await send_message("\n".join(lines))

# === Уведомления перед новостью ===
async def check_and_notify(events):
    now = datetime.now()
    for e in events:
        if e["key"] in sent_events:
            continue

        # Напоминание за 10 минут
        if e["key"] not in reminded_events and 0 < (e["datetime"] - now).total_seconds() <= 600:
            reminded_events.add(e["key"])
            await send_message(f"⏰ <b>Через 10 минут:</b> {e['title']} ({e['currency']}) в {e['datetime'].strftime('%H:%M')}")

        # Новость началась — больше не отслеживаем
        if now >= e["datetime"]:
            sent_events.add(e["key"])

# === Основной цикл ===
async def main():
    print("🚀 Бот календаря запущен.")
    await send_message("🚀 Бот успешно запущен и следит за экономическим календарём.")

    last_summary_date = None

    while True:
        now = datetime.now()
        events = fetch_events()

        # Утренний дайджест
        if now.hour == DAILY_ALERT_HOUR and (last_summary_date != now.date()):
            await send_daily_summary(events)
            last_summary_date = now.date()

        await check_and_notify(events)
        await asyncio.sleep(CHECK_INTERVAL)

# === HTTP-сервер для Render
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running.")

def run_http_server():
    server = HTTPServer(('0.0.0.0', 10000), DummyHandler)
    print("🌐 HTTP-сервер запущен на порту 10000")
    server.serve_forever()

# === Запуск
if __name__ == "__main__":
    threading.Thread(target=run_http_server, daemon=True).start()
    asyncio.run(main())
