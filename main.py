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
SYMBOL = "LTC3L_USDT"
LOG_FILE = "data_log.csv"

# === FLASK APP PARA MANTENER VIVO EL SERVICIO EN RENDER ===
app = Flask("")

@app.route("/")
def home():
    return "Bot activo y funcionando."

def run_flask():
    # Usa el puerto que Render asigna en la variable PORT
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def start_flask_thread():
    """
    Arranca Flask en un hilo separado para mantener vivo el servicio web.
    """
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print(f"✅ Flask arrancado en hilo. Escuchando en puerto {os.environ.get('PORT', '8080')}")

# === FUNCIÓN PARA OBTENER PRECIO DESDE PIONEX ===
def fetch_price():
    try:
        url = f"https://api.pionex.com/api/v1/market/ticker?symbol={SYMBOL}"
        response = requests.get(url, timeout=10)
        data = response.json()
        if "data" in data and "price" in data["data"]:
            return float(data["data"]["price"])
        else:
            print("⚠️ Respuesta inesperada de Pionex:", data)
            return None
    except Exception as e:
        print("⚠️ Error al obtener precio:", e)
        return None

# === GUARDAR PRECIO EN CSV ===
def log_price(price):
    with open(LOG_FILE, "a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([datetime.utcnow().isoformat(), SYMBOL, price])
    print(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {SYMBOL} = {price} USDT")

# === LOOP PRINCIPAL ===
def start_bot(interval=60):
    """
    Este bucle se ejecuta en el hilo principal, imprime cada minuto
    y escribe el precio en data_log.csv.
    """
    print("🔄 Iniciando bucle de monitoreo (start_bot)…")
    while True:
        try:
            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] ⏱ Obteniendo precio…")
            price = fetch_price()
            if price is not None:
                log_price(price)
            else:
                print(f"[{timestamp}] ❌ No se obtuvo precio válido.")
        except Exception as ex:
            print("⚠️ Excepción en start_bot:", ex)
        time.sleep(interval)

# === EJECUCIÓN PRINCIPAL ===
if __name__ == "__main__":
    # Creamos data_log.csv si no existe
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["timestamp", "symbol", "price"])
        print(f"🗎 Creado archivo '{LOG_FILE}' con cabecera.")

    # Arrancamos Flask en hilo para el health check del web service
    start_flask_thread()

    # Ahora arrancamos el bucle de monitoreo de precios en el hilo principal
    start_bot(interval=60)
