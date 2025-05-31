import os
import time
import requests
import csv
from flask import Flask
from threading import Thread
from binance.client import Client
from binance.exceptions import BinanceAPIException

# ========================
# CONFIGURACIÓN INICIAL
# ========================
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
PAIR = "LTCUSDT"
TRADE_AMOUNT = 11
TRADE_TRIGGER_PERCENT = 5
LOG_FILE = "data_log.csv"

print("🔐 Checking API keys...", flush=True)
if not API_KEY or not API_SECRET:
    print("❌ API keys not loaded from environment!", flush=True)
else:
    print("✅ API keys loaded.", flush=True)

client = Client(API_KEY, API_SECRET)

# ========================
# FLASK APP
# ========================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running."

def run_server():
    print("🚀 Flask server starting on port 8080...", flush=True)
    app.run(host='0.0.0.0', port=8080)

# ========================
# FAKE PING TO KEEP ALIVE
# ========================
def keep_alive_ping():
    while True:
        try:
            print("📡 Sending keep-alive ping...", flush=True)
            requests.get("https://ltc3l-breakout-bot.onrender.com")
        except Exception as e:
            print("⚠️ Keep-alive ping failed:", e, flush=True)
        time.sleep(600)

# ========================
# GET PRICE
# ========================
def get_price():
    klines = client.get_klines(symbol=PAIR, interval=Client.KLINE_INTERVAL_1HOUR, limit=2)
    price_now = float(klines[-1][4])
    price_past = float(klines[0][4])
    change_1h = ((price_now - price_past) / price_past) * 100
    return price_now, change_1h

def log_to_csv(timestamp, price, change_1h, action):
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, mode="a", newline="") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Timestamp", "Price", "1h Change (%)", "Action"])
        writer.writerow([timestamp, f"{price:.2f}", f"{change_1h:.2f}", action])

# ========================
# MONITOR & TRADE
# ========================
def monitor_and_trade():
    print("📊 Bot started. Waiting for market signals...", flush=True)
    while True:
        try:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            price, change_1h = get_price()
            print(f"[{timestamp}] Price: ${price:.2f}, 1h Change: {change_1h:.2f}%", flush=True)

            if change_1h > TRADE_TRIGGER_PERCENT:
                print(f"✅ Breakout detected! (Simulated BUY ${TRADE_AMOUNT})", flush=True)
                action = "BUY (Simulated)"
            else:
                print("⏸ No breakout. Holding.", flush=True)
                action = "HOLD"

            log_to_csv(timestamp, price, change_1h, action)

        except BinanceAPIException as e:
            print("❌ BinanceAPIException:", e, flush=True)
        except Exception as e:
            print("❌ Unexpected error:", e, flush=True)

        time.sleep(3600)

# ========================
# START EVERYTHING
# ========================
if __name__ == "__main__":
    Thread(target=run_server).start()
    Thread(target=keep_alive_ping).start()
    Thread(target=monitor_and_trade).start()
