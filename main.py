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
SYMBOL = "LTC3L_USDT"      # Par de Pionex que queremos vigilar
LOG_FILE = "data_log.csv"  # Archivo donde guardamos cada precio

# === ARCHIVO DE TRADES (para simulación de estrategia) ===
TRADES_LOG_FILE = "trades_log.csv"

# === FLASK APP PARA MANTENER VIVO EL SERVICIO EN RENDER ===
app = Flask("")

@app.route("/")
def home():
    return "Bot activo y funcionando."

def run_flask():
    """
    Arranca Flask en el puerto que Render asigne (variable PORT).
    """
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def start_flask_thread():
    """
    Lanza Flask en un hilo demonio, para que el hilo principal
    quede libre para ejecutar el bucle de monitoreo.
    """
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print(f"✅ Flask arrancado en hilo. Escuchando en puerto {os.environ.get('PORT', '8080')}")

# === FUNCIÓN PARA OBTENER PRECIO DESDE PIONEX ===
def fetch_price():
    """
    Pide el ticker a la API pública de Pionex y retorna el precio como float.
    Imprime TODO el JSON para que sepamos exactamente qué devuelve la API.
    """
    try:
        url = f"https://api.pionex.com/api/v1/market/ticker?symbol={SYMBOL}"
        response = requests.get(url, timeout=10)
        data = response.json()

        # ── Depuración: imprimimos la respuesta completa de Pionex ────────────────
        print("📦 Respuesta completa de Pionex:", data)

        # ── Si el JSON trae data.price, lo devolvemos, si no, mostramos advertencia ──
        if "data" in data and "price" in data["data"]:
            return float(data["data"]["price"])
        else:
            print("⚠️ Formato inesperado en JSON de Pionex (no hay 'data.price').")
            return None

    except Exception as e:
        print("⚠️ Error al obtener precio desde Pionex:", e)
        return None

# === GUARDAR PRECIO EN CSV ===
def log_price(price):
    """
    Escribe en data_log.csv una línea con timestamp, símbolo y precio.
    También imprime en consola la línea para saber que efectivamente guardó.
    """
    with open(LOG_FILE, "a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([datetime.utcnow().isoformat(), SYMBOL, f"{price:.8f}"])
    print(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {SYMBOL} = {price:.8f} USDT")

# === ESTRUCTURAS PARA SIMULAR PORTAFOLIO Y ESTRATEGIA (BREAKOUT APALANCADO) ===
balance_usdt = 1000.0       # Capital inicial simulado en USDT
balance_ltc3l = 0.0         # Cantidad en LTC3L (o el token que compres)
open_position = False       # Indicador de si tenemos posición abierta
entry_price = 0.0           # Precio de entrada de la posición actual
entry_amount = 0.0          # Cantidad de LTC3L comprada
historial_operaciones = []  # (Opcional) lista en memoria de operaciones

# Parámetros de estrategia:
window_size = 5             # Cantidad de iteraciones para calcular máximo local
take_profit_pct = 0.02      # 2% de ganancia
stop_loss_pct = 0.01        # 1% de pérdida
liquidation_pct = 1/3       # Para tokens 3×, ~33% abajo = liquidación

# Lista circular para guardar precios recientes (longitud = window_size)
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
    - Si hay posición abierta: comprueba take-profit, stop-loss o liquidación:
      * Take-profit: current_price >= entry_price * (1 + take_profit_pct)
      * Stop-loss: current_price <= entry_price * (1 - stop_loss_pct)
      * Liquidación: current_price <= entry_price * (1 - liquidation_pct)
      Si se cumple cualquiera, cierra toda la posición (SELL o LIQUIDACIÓN) y registra en trades_log.csv.
    """
    global balance_usdt, balance_ltc3l, open_position, entry_price, entry_amount

    # 1) Si no tenemos posición abierta, intentamos abrirla en breakout
    if not open_position:
        recent_prices.append(current_price)

        if len(recent_prices) > window_size:
            # Mantenemos sólo los últimos window_size valores
            recent_prices.pop(0)

            # Calculamos el máximo de las iteraciones anteriores (excluyendo la actual)
            max_prev = max(recent_prices[:-1])
            # Definimos umbral de breakout
            threshold = max_prev  # podrías usar max_prev * 1.001 para un margen extra

            if current_price > threshold:
                # Abrir posición simulando apalancamiento 3×
                # En este simul, simplemente compramos "entry_amount = capital / precio"
                entry_amount = balance_usdt / entry_price if entry_price != 0 else balance_usdt / current_price
                # En realidad, si fuese apalancado 3×, comprarías 3× el capital, pero
                # aquí asumimos que el PnL ya está potenciado. Para simplificar:
                entry_amount = balance_usdt / current_price

                balance_usdt_pre = balance_usdt
                balance_ltc3l = entry_amount
                balance_usdt = 0.0
                entry_price = current_price
                open_position = True

                # Registrar BUY
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
                print(f"💼 [Estrategia] Compré {entry_amount:.8f} LTC3L a {current_price:.4f} USDT (breakout).")

    else:
        # 2) Si ya hay posición abierta, calculamos TP, SL y precio de liquidación
        tp_price = entry_price * (1 + take_profit_pct)
        sl_price = entry_price * (1 - stop_loss_pct)
        liquidation_price = entry_price * (1 - liquidation_pct)

        # 2.a) Liquidación forzosa
        if current_price <= liquidation_price:
            balance_usdt_pre = balance_usdt
            balance_ltc3l_pre = balance_ltc3l

            # Perdemos todo el capital simulado
            balance_usdt = 0.0
            balance_ltc3l = 0.0
            profit = - (entry_amount * entry_price)  # pérdida total del capital

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

            print(f"🛑 [Estrategia] ¡Liquidación! Precio {current_price:.4f}. Pérdida total = {profit:.4f} USDT.")

        # 2.b) Take-profit o Stop-loss
        elif current_price >= tp_price or current_price <= sl_price:
            balance_usdt_pre = balance_usdt
            balance_ltc3l_pre = balance_ltc3l

            close_amount = balance_ltc3l
            balance_usdt = close_amount * current_price  # convertimos todo a USDT
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
            print(f"✂️ [Estrategia] {etiqueta}. Vendí {close_amount:.8f} LTC3L a {current_price:.4f} USDT; PnL = {profit:.4f} USDT.")
        else:
            # No cumple ningún criterio de cierre; seguimos en posición
            print(f"🔒 [Estrategia] Posición abierta. Precio actual {current_price:.4f}, esperando TP/SL.")

# === LOOP PRINCIPAL DE MONITOREO Y SIMULACIÓN ===
def start_bot(interval=60):
    """
    Bucle infinito:
      1) Imprime claramente el inicio de la iteración.
      2) Llama a fetch_price() y, si hay precio, lo graba en CSV.
      3) Llama a strategy_engine(price) para simular trading.
      4) Duerme `interval` segundos antes de repetir.
    """
    print("🔄 Iniciando bucle de monitoreo y simulación (start_bot)…")
    while True:
        try:
            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n======= [{timestamp}] INICIO DE ITERACIÓN OBTENIENDO PRECIO =======")

            price = fetch_price()
            if price is not None:
                log_price(price)
                strategy_engine(price)
            else:
                print(f"⚠️ A las {timestamp}, no se obtuvo precio válido.")

            print(f"======= [FIN DE ITERACIÓN] =================================================\n")
        except Exception as ex:
            print("⚠️ Excepción en start_bot:", ex)

        time.sleep(interval)

# === EJECUCIÓN PRINCIPAL ===
if __name__ == "__main__":
    # 1) Crear data_log.csv si no existe
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["timestamp", "symbol", "price"])
        print(f"🗎 Creado archivo '{LOG_FILE}' con cabecera.")

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
        print(f"🗎 Creado archivo '{TRADES_LOG_FILE}' con cabecera.")

    # 3) Arrancar Flask en hilo demonio para mantener vivo el servicio
    start_flask_thread()

    # 4) Arrancar el bucle principal con intervalo de 60 segundos
    start_bot(interval=60)
