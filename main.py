import os
import time
import requests
from flask import Flask
from threading import Thread

# Configuración
ASSET_NAME = "litecoin"
PAIR = "ltc3l"import os
from flask import Flask
from threading import Thread
import time
import requests
import csv
from binance.client import Client
from binance.exceptions import BinanceAPIException

# CONFIGURACIÓN
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
PAIR = "LTCUSDT"
TRADE_AMOUNT = 11
TRADE_TRIGGER_PERCENT = 5

client = Client(API_KEY, API_SECRET)

# Keep-alive server
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running."

def run_server():
    app.run(host='0.0.0.0', port=8080)

# Keep-alive ping
def keep_alive_ping():
    while True:
        try:
            requests.get("https://ltc3l-breakout-bot.onrender.com")
        except:
            pass
        time.sleep(600)  # Cada 10 minutos

# Obtener precio actual y cambio en 1h
def get_price():
    klines = client.get_klines(symbol=PAIR, interval=Client.KLINE_INTERVAL_1HOUR, limit=2)
    price_now = float(klines[-1][4])  # cierre actual
    price_past = float(klines[0][4])  # cierre 1h atrás
    change_1h = ((price_now - price_past) / price_past) * 100
    return price_now, change_1h

# Guardar log CSV
def log_to_csv(timestamp, price, change_1h, action):
    file_exists = os.path.isfile("data_log.csv")
    with open("data_log.csv", mode="a", newline="") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Timestamp", "Price", "1h Change", "Action"])
        writer.writerow([timestamp, f"${price:.2f}", f"{change_1h:.2f}%", action])

# Estrategia principal
def monitor_and_trade():
    while True:
        try:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            price, change_1h = get_price()
            print(f"[{timestamp}] Price: ${price:.2f}")

            if change_1h > TRADE_TRIGGER_PERCENT:
                print(f"📈 1h change: {change_1h:.2f}%")
                print(f"🚀 SIMULATED TRADE ENTERED: Buying {PAIR.upper()} with ${TRADE_AMOUNT}")
                log_to_csv(timestamp, price, change_1h, "BUY (Simulated)")
            else:
                print(f"📉 No breakout. Holding...")
                log_to_csv(timestamp, price, change_1h, "HOLD")

        except BinanceAPIException as e:
            print("Binance error:", e)
        except Exception as e:
            print("Unexpected error:", e)

        time.sleep(3600)  # Cada 1h

# Lanzar todos los hilos
if __name__ == "__main__":
    Thread(target=run_server).start()
    Thread(target=keep_alive_ping).start()
    monitor_and_trade()

TRADE_AMOUNT = 11
POLLING_INTERVAL = 600  # cada 10 minutos
RENDER_URL = "https://ltc3l-breakout-bot.onrender.com"  # <- Pega tu URL exacta aquí si cambia

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running."

def run_server():
    app.run(host='0.0.0.0', port=8080)

def keep_alive_ping():
    while True:
        try:
            requests.get(RENDER_URL)
        except:
            pass
        time.sleep(POLLING_INTERVAL)

def get_price():
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ASSET_NAME}&vs_currencies=usd&include_24hr_change=true&include_1hr_change=true"
    response = requests.get(url)
    data = response.json()
    return data[ASSET_NAME]['usd'], data[ASSET_NAME]['usd_1h_change']

def monitor_and_trade():
    while True:
        try:
            price, change_1h = get_price()
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] Price: ${price:.2f}")

            if change_1h > 5:
                print(f"📈 1h change: {change_1h:.2f}%")
                print(f"🚀 SIMULATED TRADE ENTERED: Buying {PAIR.upper()} with ${TRADE_AMOUNT}")
            else:
                print(f"📉 No breakout. Holding...")

        except Exception as e:
            print(f"Error fetching price: {e}")

        time.sleep(POLLING_INTERVAL)

# Inicia todo
if __name__ == '__main__':
    Thread(target=run_server).start()
    Thread(target=keep_alive_ping).start()
    monitor_and_trade()
