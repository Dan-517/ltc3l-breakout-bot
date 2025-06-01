```python
from datetime import datetime, timedelta
import csv
import os
import requests
from flask import Flask, send_file
from threading import Thread
import time

# === 1. CONFIG Y MÓDULO DE DATOS & LOGGING ===

API_KEY = os.environ.get("PIONEX_API_KEY")
API_SECRET = os.environ.get("PIONEX_API_SECRET")

SYMBOL = "SOL_USDT"            # Par SOL/USDT
INTERVAL = "60M"               # Velas de 1 hora
LOOKBACK = 20                  # Ventana de ruptura: últimas 20 velas
EMA_PERIOD = 200               # EMA de 200 periodos
ATR_PERIOD = 14                # ATR de 14 periodos
VOLUME_MULTIPLIER = 1.2        # Volumen_actual ≥ promedio_20h * 1.2
ATR_SL_MULT = 0.5              # Stop‐loss = Low_N – ATR_14 * 0.5
ATR_TP_MULT = 2.0              # Take‐profit = price + ATR_14 * 2.0
RISK_PERCENT = 0.01            # Riesgo 1 % del balance por operación

LOG_FILE = "data_log.csv"
TRADES_LOG_FILE = "trades_log.csv"
ERRORS_LOG = "errors.log"

app = Flask("")

@app.route("/")
def home():
    return "Bot de Breakout SOL/USDT activo."

@app.route("/download/data")
def download_data():
    return send_file(LOG_FILE, as_attachment=True)

@app.route("/download/trades")
def download_trades():
    return send_file(TRADES_LOG_FILE, as_attachment=True)


def fetch_klines(symbol, interval, limit=210):
    """
    Obtiene las últimas `limit` velas del par `symbol` con intervalo `interval`.
    Retorna la lista de diccionarios:
      { "time": ..., "open": "...", "close": "...", "high": "...", "low": "...", "volume": "..." }
    """
    try:
        url = f"https://api.pionex.com/api/v1/market/klines?symbol={symbol}&interval={interval}&limit={limit}"
        response = requests.get(url, timeout=10)
        data = response.json()
        if data.get("result") and "klines" in data["data"]:
            return data["data"]["klines"]
        else:
            raise ValueError(f"fetch_klines: JSON inesperado o sin 'klines': {data}")
    except Exception as e:
        with open(ERRORS_LOG, "a") as ef:
            ef.write(f"{datetime.utcnow().isoformat()} - ERROR fetch_klines: {e}\n")
        return None


def log_price_entry(timestamp, symbol, price, High_N, Low_N, ATR_14, volume_recent, volume_avg):
    """
    Registra en data_log.csv una fila con:
      timestamp, symbol, price_entry, High_N, Low_N, ATR_14, volume_actual, volume_avg_20h
    """
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            timestamp, symbol,
            f"{price:.8f}",
            f"{High_N:.8f}",
            f"{Low_N:.8f}",
            f"{ATR_14:.8f}",
            f"{volume_recent:.8f}",
            f"{volume_avg:.8f}"
        ])
    print(f"[{timestamp}] LOG_PRICE: {symbol} @ {price:.8f} | High_N={High_N:.8f}, Low_N={Low_N:.8f}, ATR_14={ATR_14:.8f}, Vol={volume_recent:.2f}/{volume_avg:.2f}", flush=True)


def write_trade(action, symbol, price, size,
                sl, tp,
                balance_usdt_pre, balance_sol_pre,
                balance_usdt_post, balance_sol_post,
                pnl):
    """
    Registra en trades_log.csv cada operación (BUY o SELL).
    Columns:
      timestamp, action, symbol, price, size, stop_loss, take_profit,
      balance_usdt_pre, balance_sol_pre, balance_usdt_post, balance_sol_post, pnl
    """
    with open(TRADES_LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.utcnow().isoformat(),
            action,
            symbol,
            f"{price:.8f}",
            f"{size:.8f}",
            f"{sl:.8f}",
            f"{tp:.8f}",
            f"{balance_usdt_pre:.8f}",
            f"{balance_sol_pre:.8f}",
            f"{balance_usdt_post:.8f}",
            f"{balance_sol_post:.8f}",
            f"{pnl:.8f}"
        ])
    print(f"💰 TRADE {action}: {symbol} size={size:.8f} @ {price:.8f} | SL={sl:.8f}, TP={tp:.8f}, PnL={pnl:.8f}", flush=True)


# ---------------------------------------
# 2. MÓDULO DE ESTRATEGIA
# ---------------------------------------

balance_usdt = 1000.0       # Capital inicial en USDT simulado
balance_sol = 0.0           # Cantidad de SOL en posición simulada
open_position = False
entry_price = 0.0
entry_size = 0.0
stop_loss = 0.0
take_profit = 0.0

def calculate_EMA(closes, period):
    """
    Calcula la EMA de `period` para la lista de precios `closes`.
    Suponemos que len(closes) >= period.
    """
    sma = sum(closes[0:period]) / period
    ema = sma
    alpha = 2 / (period + 1)
    for price in closes[period:]:
        ema = alpha * price + (1 - alpha) * ema
    return ema

def calculate_ATR(klines, period):
    """
    Calcula el ATR de `period` para las velas `klines` que ya incluyan al menos period+1 elementos.
    klines: lista de diccionarios con keys "high", "low", "close". 
    Retorna ATR simple (promedio de TRs) de los últimos `period` periodos.
    """
    tr_list = []
    highs = [float(k["high"]) for k in klines]
    lows = [float(k["low"]) for k in klines]
    closes = [float(k["close"]) for k in klines]
    for i in range(-period, 0):
        prev_close = closes[i - 1]
        current_high = highs[i]
        current_low = lows[i]
        tr = max(
            current_high - current_low,
            abs(current_high - prev_close),
            abs(current_low - prev_close)
        )
        tr_list.append(tr)
    return sum(tr_list) / period

def strategy_breakout():
    """
    Lógica de estrategia de breakout en SOL/USDT cada cierre de vela de 1h.
    1) Descarga últimas 210 velas de 1h.
    2) Calcula High_N, Low_N basados en últimas LOOKBACK velas anteriores al cierre actual.
    3) Calcula ATR_14, EMA_200 y volumen promedio de últimas 20 velas.
    4) Si no hay posición abierta, evalúa condiciones de entrada:
         - price_now > High_N
         - price_now > EMA_200
         - vol_actual >= vol_avg_20h * VOLUME_MULTIPLIER
       Si cumple, abre posición simulated BUY.
    5) Si hay posición abierta, gestiona SL/TP/trailing stop:
         - Si price_now <= stop_loss → vende (cerrar posición).
         - Si price_now >= take_profit → vende.
         - Opcional: actualizar trailing stop si price sube +1 ATR.
    6) Registra en CSV cada acción.
    """
    global balance_usdt, balance_sol, open_position, entry_price, entry_size, stop_loss, take_profit

    klines = fetch_klines(SYMBOL, INTERVAL, limit=210)
    if klines is None or len(klines) < EMA_PERIOD + 1:
        print("⚠️ strategy_breakout: No se obtuvieron suficientes velas para calcular indicadores.", flush=True)
        return

    closes = [float(k["close"]) for k in klines]
    highs = [float(k["high"]) for k in klines]
    lows = [float(k["low"]) for k in klines]
    volumes = [float(k["volume"]) for k in klines]

    last_idx = -1

    window_highs = highs[-LOOKBACK-1:-1]
    window_lows = lows[-LOOKBACK-1:-1]
    High_N = max(window_highs)
    Low_N = min(window_lows)

    volume_recent = volumes[-1]
    volume_avg_20h = sum(volumes[-LOOKBACK-1:-1]) / LOOKBACK

    ATR_14 = calculate_ATR(klines[-(ATR_PERIOD+1):], ATR_PERIOD)

    closes_for_ema = closes[-(EMA_PERIOD + 10):] if len(closes) >= EMA_PERIOD + 10 else closes[-EMA_PERIOD:]
    EMA_200 = calculate_EMA(closes_for_ema, EMA_PERIOD)

    price_now = closes[-1]
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    log_price_entry(timestamp, SYMBOL, price_now, High_N, Low_N, ATR_14, volume_recent, volume_avg_20h)

    if not open_position:
        if (
            price_now > High_N
            and price_now > EMA_200
            and volume_recent >= volume_avg_20h * VOLUME_MULTIPLIER
        ):
            stop_loss = Low_N - ATR_14 * ATR_SL_MULT
            take_profit = price_now + ATR_14 * ATR_TP_MULT

            risk_amount = balance_usdt * RISK_PERCENT
            distance_to_sl = price_now - stop_loss
            if distance_to_sl <= 0:
                print("⚠️ strategy_breakout: distance_to_sl <= 0, no abro posición.", flush=True)
                return
            size = risk_amount / distance_to_sl

            balance_usdt_pre = balance_usdt
            balance_sol_pre = balance_sol
            balance_sol = size
            balance_usdt = 0.0
            entry_price = price_now
            entry_size = size
            open_position = True

            write_trade(
                action="BUY",
                symbol=SYMBOL,
                price=price_now,
                size=size,
                sl=stop_loss,
                tp=take_profit,
                balance_usdt_pre=balance_usdt_pre,
                balance_sol_pre=balance_sol_pre,
                balance_usdt_post=balance_usdt,
                balance_sol_post=balance_sol,
                pnl=0.0
            )
        else:
            print(f"🔍 [{timestamp}] No cumple condiciones de entrada. price={price_now:.4f}, High_N={High_N:.4f}, EMA200={EMA_200:.4f}, vol={volume_recent:.2f}/{volume_avg_20h:.2f}", flush=True)
    else:
        balance_usdt_pre = balance_usdt
        balance_sol_pre = balance_sol

        if price_now <= stop_loss:
            pnl = (price_now - entry_price) * entry_size
            balance_usdt = entry_size * price_now
            balance_sol = 0.0
            open_position = False

            write_trade(
                action="SELL",
                symbol=SYMBOL,
                price=price_now,
                size=entry_size,
                sl=stop_loss,
                tp=take_profit,
                balance_usdt_pre=balance_usdt_pre,
                balance_sol_pre=balance_sol_pre,
                balance_usdt_post=balance_usdt,
                balance_sol_post=balance_sol,
                pnl=pnl
            )

        elif price_now >= take_profit:
            pnl = (price_now - entry_price) * entry_size
            balance_usdt = entry_size * price_now
            balance_sol = 0.0
            open_position = False

            write_trade(
                action="SELL",
                symbol=SYMBOL,
                price=price_now,
                size=entry_size,
                sl=stop_loss,
                tp=take_profit,
                balance_usdt_pre=balance_usdt_pre,
                balance_sol_pre=balance_sol_pre,
                balance_usdt_post=balance_usdt,
                balance_sol_post=balance_sol,
                pnl=pnl
            )

        else:
            if price_now >= entry_price + ATR_14:
                new_sl = price_now - ATR_14 * 0.75
                if new_sl > stop_loss:
                    stop_loss = new_sl
                    print(f"🔄 [TRAILING STOP] Nueva SL actualizada a {stop_loss:.4f}", flush=True)
            else:
                print(f"🔒 [POSICIÓN ABIERTA] No se alcanza SL/TP. price={price_now:.4f}, SL={stop_loss:.4f}, TP={take_profit:.4f}", flush=True)


# ---------------------------------------
# 3. LOOP PRINCIPAL + FLASK
# ---------------------------------------

def seconds_until_next_hour():
    now = datetime.utcnow()
    next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return (next_hour - now).total_seconds()

def start_bot():
    """
    Ejecuta strategy_breakout() de inmediato, luego duerme hasta el próximo cierre de vela 1h,
    y a partir de ahí cada vez que se cierre una hora completa vuelve a llamar a strategy_breakout().
    """
    print("🔄 Iniciando bucle de monitoreo (primera ejecución inmediata)…", flush=True)
    try:
        print(f"\n======= [{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] PRIMERA EJECUCIÓN INMEDIATA =======", flush=True)
        strategy_breakout()
    except Exception as e:
        with open(ERRORS_LOG, "a") as ef:
            ef.write(f"{datetime.utcnow().isoformat()} - ERROR primera ejecución: {e}\n")
        print(f"⚠️ Excepción en primera ejecución: {e}", flush=True)

    delay = seconds_until_next_hour()
    print(f"💤 Durmiendo {int(delay)} s hasta el siguiente cierre de vela (top of hour).", flush=True)
    time.sleep(delay)

    while True:
        try:
            print(f"\n======= [{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] NUEVA VELA 1H CERRÓ =======", flush=True)
            strategy_breakout()
        except Exception as e:
            with open(ERRORS_LOG, "a") as ef:
                ef.write(f"{datetime.utcnow().isoformat()} - Excepción en start_bot: {e}\n")
            print(f"⚠️ Excepción en start_bot: {e}", flush=True)

        delay = seconds_until_next_hour()
        print(f"💤 Durmiendo {int(delay)} s hasta el siguiente cierre de vela.", flush=True)
        time.sleep(delay)

if __name__ == "__main__":
    # 1) Crear data_log.csv si no existe
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as f:
            csv.writer(f).writerow(["timestamp", "symbol", "price", "High_N", "Low_N", "ATR_14", "vol_current", "vol_avg_20h"])
        print(f"🗎 Creado '{LOG_FILE}' con cabecera.", flush=True)

    # 2) Crear trades_log.csv si no existe
    if not os.path.exists(TRADES_LOG_FILE):
        with open(TRADES_LOG_FILE, "w", newline="") as f:
            csv.writer(f).writerow([
                "timestamp", "action", "symbol", "price", "size", "stop_loss", "take_profit",
                "balance_usdt_pre", "balance_sol_pre", "balance_usdt_post", "balance_sol_post", "pnl"
            ])
        print(f"🗎 Creado '{TRADES_LOG_FILE}' con cabecera.", flush=True)

    # 3) Arrancar el bucle principal de trading en un hilo demonio
    bot_thread = Thread(target=start_bot)
    bot_thread.daemon = True
    bot_thread.start()

    # 4) Arrancar Flask en el hilo principal
    port = int(os.environ.get("PORT", 8080))
    print(f"✅ Arrancando Flask en el hilo principal en el puerto {port}", flush=True)
    app.run(host="0.0.0.0", port=port)
```
