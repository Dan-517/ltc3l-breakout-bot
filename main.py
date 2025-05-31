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
SYMBOL = "LTC3L_USDT"  # Par de Pionex a monitorear
LOG_FILE = "data_log.csv"

# === FLASK APP PARA MANTENER VIVO EL SERVICIO EN RENDER ===
app = Flask("")

@app.route("/")
def home():
    return "Bot activo y funcionando."

def run_flask():
    # Obtiene el puerto de RENDER, o 8080 por defecto
    port = int(os.environ.get("PORT", 8080))
    # Ejecuta Flask en 0.0.0.0 para que sea accesible externamente
    app.run(host="0.0.0.0", port=port)

def start_flask_thread():
    """
    Arranca Flask en un hilo separado para mantener vivo el servicio sin bloquear
    el hilo principal donde correrá el bot.
    """
    t = Thread(target=run_flask)
    t.daemon = True       # Si el hilo principal muere, esto termina también
    t.start()
    print(f"✅ Flask arrancado en hilo. Esperando peticiones en puerto {os.environ.get('PORT', '8080')}")

# === FUNCIÓN PARA OBTENER PRECIO DESDE PIONEX ===
def fetch_price():
    try:
        url = f"https://api.pionex.com/api/v1/market/ticker?symbol={SYMBOL}"
        response = requests.get(url, timeout=10)
        data = response.json()
        # Pionex devuelve {"code":0,"message":"success","data":{...}}
        # Asegurémonos de que existe data y price dentro
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
    """
    Escribe una línea en LOG_FILE con timestamp, símbolo y precio.
    También imprime en consola para debug.
    """
    with open(LOG_FILE, "a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([datetime.utcnow().isoformat(), SYMBOL, price])
    print(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {SYMBOL} = {price} USDT")

# === LOOP PRINCIPAL ===
def start_bot(interval=60):
    """
    Bucle infinito que cada `interval` segundos:
    1) llama a fetch_price()
    2) si obtuvo precio, lo graba en CSV
    3) duerme `interval` segundos
    """
    print("🔄 Iniciando bucle de monitoreo (start_bot). Cada", interval, "s estará obteniendo precio…")
    while True:
        try:
            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] ⏱ Obteniendo precio…")
            price = fetch_price()
            if price is not None:
                log_price(price)
            else:
                print(f"[{timestamp}] ❌ No se obtuvo precio válido. Se omite escritura.")
        except Exception as ex:
            print("⚠️ Excepción atrapada dentro de start_bot:", ex)
        # Esperar intervalo antes de la próxima iteración
        time.sleep(interval)

# === EJECUCIÓN PRINCIPAL ===
if __name__ == "__main__":
    # Si no existe el archivo CSV, lo creamos con header
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["timestamp", "symbol", "price"])
        print(f"🗎 Creado archivo de logs '{LOG_FILE}' con cabecera.")

    # Arrancamos Flask en un hilo separado (mantiene viva la app web)
    start_flask_thread()

    # Ejecutamos el loop principal en el hilo principal
    start_bot(interval=60)
