from datetime import datetime
import csv
import os
import requests
from flask import Flask
from threading import Thread
import time
import sys

# === CONFIGURACIÓN DE ENTORNO ===
API_KEY = os.environ.get("PIONEX_API_KEY")
API_SECRET = os.environ.get("PIONEX_API_SECRET")

# === CONFIGURACIÓN DEL ASSET A MONITOREAR ===
SYMBOL = "LTC3L_USDT"
LOG_FILE = "data_log.csv"

# === ARCHIVO DE TRADES (para simulación de estrategia) ===
TRADES_LOG_FILE = "trades_log.csv"

# === FLASK APP PARA MANTENER VIVO EL SERVICIO EN RENDER ===
app = Flask("")

@app.route("/")
def home():
    return "Bot activo y funcionando."

def fetch_price():
    """
    Pide el ticker a la API pública de Pionex, imprime antes y después de la llamada
    para depurar bloqueos. Retorna el precio como float si todo va bien.
    """
    try:
        # Print de diagnóstico que sale inmediatamente
        print("🔍 [fetch_price] Llamando a Pionex API...", flush=True)
        url = f"https://api.pionex.com/api/v1/market/ticker?symbol={SYMBOL}"
        response = requests.get(url, timeout=10)
        data = response.json()
        print("✅ [fetch_price] Respuesta recibida de Pionex.", flush=True)
        print("📦 Respuesta completa de Pionex:", data, flush=True)

        if "data" in data and "price" in data["data"]:
            return float(data["data"]["price"])
        else:
            print("⚠️ Formato inesperado en JSON de Pionex (no hay 'data.price').", flush=True)
            return None
    except Exception as e:
        print("⚠️ Error al obtener precio desde Pionex:", e, flush=True)
        return None

def log_price(price):
    """
    Escribe en data_log.csv una línea con timestamp, símbolo y precio.
    También imprime en consola la línea para saber que efectivamente guardó.
    """
    with open(LOG_FILE, "a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([datetime.utcnow().isoformat(), SYMBOL, f"{price:.8f}"])
    print(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {SYMBOL} = {price:.8f} USDT", flush=True)

# === ESTRUCTURAS PARA SIMULAR PORTAFOLIO Y ESTRATEGIA (BREAKOUT APALANCADO) ===
balance_usdt = 1000.0
balance_ltc3l = 0.0
open_position = False
entry_price = 0.0
entry_amount = 0.0

window_size = 5
take_profit_pct = 0.02
stop_loss_pct = 0.01
liquidation_pct = 1/3

recent_prices = []

def write_trade(action, price, amount,
                balance_usdt_pre, balance_ltc3l_pre,
                balance_usdt_post, balance_ltc3l_post,
                profit_loss):
    """
    Registra cada operación simulada en trades_log.csv.
    """
    timestamp = datetime.utcnow().isoformat()
    with open(TRADES_LOG_FILE, "a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([
            timestamp,
            action,
            f"{price:.8f}",
            f"{amount:.8f}",
            f"{balance_usdt_pre:.8f}",
            f"{balance_ltc3l_pre:.8f}",
            f"{balance_usdt_post:.8f}",
            f"{balance_ltc3l_post:.8f}",
            f"{profit_loss:.8f}"
        ])

def strategy_engine(current_price):
    """
    Motor de estrategia de breakout con apalancamiento 3×.
    - Si no hay posición: verifica si current_price rompe el máximo de las últimas window_size iteraciones.
      Si rompe, compra todo el capital simulado (USDT) en LTC3L y registra BUY.
    - Si hay posición: comprueba TP, SL o liquidación y cierra la posición si corresponde.
    """
    global balance_usdt, balance_ltc3l, open_position, entry_price, entry_amount

    if not open_position:
        recent_prices.append(current_price)
        if len(recent_prices) > window_size:
            recent_prices.pop(0)
            max_prev = max(recent_prices[:-1])
            threshold = max_prev
            if current_price > threshold:
                entry_amount = balance_usdt / current_price
                balance_usdt_pre = balance_usdt
                balance_ltc3l = entry_amount
                balance_usdt = 0.0
                entry_price = current_price
                open_position = True

                write_trade(
                    action="BUY",
                    price=current_price,
                    amount=entry_amount,
                    balance_usdt_pre=balance_usdt_pre,
                    balance_ltc3l_pre=0.0,
                    balance_usdt_post=balance_usdt,
                    balance_ltc3l_post=balance_ltc3l,
                    profit_loss=0.0
                )
                print(f"💼 [Estrategia] Compré {entry_amount:.8f} LTC3L a {current_price:.4f} USDT (breakout).", flush=True)
    else:
        tp_price = entry_price * (1 + take_profit_pct)
        sl_price = entry_price * (1 - stop_loss_pct)
        liquidation_price = entry_price * (1 - liquidation_pct)

        if current_price <= liquidation_price:
            balance_usdt_pre = balance_usdt
            balance_ltc3l_pre = balance_ltc3l
            balance_usdt = 0.0
            balance_ltc3l = 0.0
            profit = - (entry_amount * entry_price)

            write_trade(
                action="LIQUIDACIÓN",
                price=current_price,
                amount=entry_amount,
                balance_usdt_pre=balance_usdt_pre,
                balance_ltc3l_pre=balance_ltc3l_pre,
                balance_usdt_post=balance_usdt,
                balance_ltc3l_post=balance_ltc3l,
                profit_loss=profit
            )
            open_position = False
            entry_price = 0.0
            entry_amount = 0.0

            print(f"🛑 [Estrategia] ¡Liquidación! Precio {current_price:.4f}. Pérdida total = {profit:.4f} USDT.", flush=True)

        elif current_price >= tp_price or current_price <= sl_price:
            balance_usdt_pre = balance_usdt
            balance_ltc3l_pre = balance_ltc3l
            close_amount = balance_ltc3l
            balance_usdt = close_amount * current_price
            balance_ltc3l = 0.0
            profit = balance_usdt - (entry_amount * entry_price)

            write_trade(
                action="SELL",
                price=current_price,
                amount=close_amount,
                balance_usdt_pre=balance_usdt_pre,
                balance_ltc3l_pre=balance_ltc3l_pre,
                balance_usdt_post=balance_usdt,
                balance_ltc3l_post=balance_ltc3l,
                profit_loss=profit
            )
            open_position = False
            entry_price = 0.0
            entry_amount = 0.0

            etiqueta = "TP" if current_price >= tp_price else "SL"
            print(f"✂️ [Estrategia] {etiqueta}. Vendí {close_amount:.8f} LTC3L a {current_price:.4f} USDT; PnL = {profit:.4f} USDT.", flush=True)
        else:
            print(f"🔒 [Estrategia] Posición abierta. Precio actual {current_price:.4f}, esperando TP/SL.", flush=True)

def start_bot(interval=60):
    """
    Bucle infinito que cada `interval` segundos:
      1) Imprime inicio de iteración.
      2) Ejecuta fetch_price → log_price → strategy_engine.
      3) Imprime “Esperando X segundos…” y duerme `interval`.
    """
    print("🔄 Iniciando bucle de monitoreo y simulación (start_bot)…", flush=True)
    while True:
        try:
            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n======= [{timestamp}] INICIO DE ITERACIÓN OBTENIENDO PRECIO =======", flush=True)

            price = fetch_price()
            if price is not None:
                log_price(price)
                strategy_engine(price)
            else:
                print(f"⚠️ A las {timestamp}, no se obtuvo precio válido.", flush=True)

            print(f"======= [FIN DE ITERACIÓN] =================================================\n", flush=True)
            # Mensaje que comprueba que entramos al sleep, de modo que no parezca “estático”
            print(f"💤 Esperando {interval} segundos antes de la siguiente iteración…", flush=True)
        except Exception as ex:
            print("⚠️ Excepción en start_bot:", ex, flush=True)

        time.sleep(interval)

if __name__ == "__main__":
    # 1) Crear data_log.csv si no existe
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["timestamp", "symbol", "price"])
        print(f"🗎 Creado archivo '{LOG_FILE}' con cabecera.", flush=True)

    # 2) Crear trades_log.csv si no existe
    if not os.path.exists(TRADES_LOG_FILE):
        with open(TRADES_LOG_FILE, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([
                "timestamp", "action", "price", "amount",
                "balance_usdt_pre", "balance_ltc3l_pre",
                "balance_usdt_post", "balance_ltc3l_post",
                "profit_loss"
            ])
        print(f"🗎 Creado archivo '{TRADES_LOG_FILE}' con cabecera.", flush=True)

    # 3) Arrancar el bucle principal en un hilo demonio
    bot_thread = Thread(target=start_bot, args=(60,))
    bot_thread.daemon = True
    bot_thread.start()

    # 4) Arrancar Flask en el hilo principal (app.run bloquea aquí)
    port = int(os.environ.get("PORT", 8080))
    print(f"✅ Arrancando Flask en el hilo principal en el puerto {port}", flush=True)
    app.run(host="0.0.0.0", port=port)
