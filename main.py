import os
import time
import requests
import csv
from flask import Flask
from threading import Thread
from binance.client import Client
from binance.exceptions import BinanceAPIException

# CONFIGURACIÓN
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
PAIR = "LTCUSDT"
TRADE_AMOUNT = 11
TRADE_TRIGGER_PERCENT = 5  # % de cambio en 1h para hacer breakout
LOG_FILE = "data_log.csv"

client = Client(API_KEY, API_SECRET)

# Servidor Flask para mantener activo
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running."

def run_server():
    app.run(host='0.0.0.0', port=8080)

# Ping falso para que Render no duerma
def keep_alive_ping():
    while True:
        try:
            requests.get("https://ltc3l-breakout-bot.onrender.com")
        except:
            pass
        time.sleep(600)  # cada 10 minutos

# Obtener precio actual y cambio en 1 hora
def get_price():
    klines = client.get_klines(symbol=PAIR, interval=Client.KLINE_INTERVAL_1HOUR, limit=2)
    price_now = float(klines[-1][4])  # cierre actual
    price_past = float(klines[0][4])  # cierre 1h atrás
    change_1h = ((price_now - price_past) / price_past) * 100
    return price_now, change_1h

# Guardar log CSV
def log_to_csv(timestamp, price, change_1h, action):
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, mode="a", newline="") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Timestamp", "Price", "1h Change (%)", "Action"])
        writer.writerow([timestamp, f"{price:.2f}", f"{change_1h:.2f}", action])

# Estrategia de breakout
def monitor_and_trade():
    while True:
        try:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            price, change_1h = get_price()
            print(f"[{timestamp}] Price: ${price:.2f}, Change 1h: {change_1h:.2f}%")

            if change_1h > TRADE_TRIGGER_PERCENT:
                print(f"🚀 Breakout detected! Simulated BUY with ${TRADE_AMOUNT}")
                action = "BUY (Simulated)"
            else:
                print("📉 No breakout. Holding.")
                action = "HOLD"

            log_to_csv(timestamp, price, change_1h, action)

        except BinanceAPIException as e:
            print("Binance error:", e)
        except Exception as e:
            print("Unexpected error:", e)

        time.sleep(3600)  # cada 1 hora real (puedes bajar a 60 para testeo)

# Lanzar todo como hilos
if __name__ == "__main__":
    Thread(target=run_server).start()
    Thread(target=keep_alive_ping).start()
    Thread(target=monitor_and_trade).start()
