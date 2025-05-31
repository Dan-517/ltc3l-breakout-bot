from datetime import datetime
import csv
import os
import requests
from flask import Flask
from threading import Thread
import time

# === CONFIGURACIÓN DE ENTORNO ===
API_KEY = os.environ.get("PIONEX_API_KEY")
API_SECRET = os.environ.get("PIONEX_API_SECRET")

# === CONFIGURACIÓN DEL ASSET A MONITOREAR ===
SYMBOL = "LTC3L_USDT"  # Puedes cambiar este par por otro de Pionex
LOG_FILE = "data_log.csv"

# === FLASK APP PARA MANTENER VIVO EL SERVICIO EN RENDER ===
app = Flask("")

@app.route("/")
def home():
    return "Bot activo y funcionando."

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# === FUNCIÓN PARA OBTENER PRECIO DESDE PIONEX ===
def fetch_price():
    try:
        url = f"https://api.pionex.com/api/v1/market/ticker?symbol={SYMBOL}"
        response = requests.get(url)
        data = response.json()
        return float(data["data"]["price"])
    except Exception as e:
        print("Error al obtener precio:", e)
        return None

# === GUARDAR PRECIO EN CSV ===
def log_price(price):
    with open(LOG_FILE, "a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([datetime.now().isoformat(), SYMBOL, price])
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {SYMBOL} = {price} USDT")

# === LOOP PRINCIPAL ===
def start_bot(interval=60):
    while True:
        price = fetch_price()
        if price:
            log_price(price)
        time.sleep(interval)

# === EJECUCIÓN PRINCIPAL ===
if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["timestamp", "symbol", "price"])

    keep_alive()
    start_bot(interval=60)
