import os
import time
import requests
from flask import Flask
from threading import Thread

# Configuración
ASSET_NAME = "litecoin"
PAIR = "ltc3l"
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
