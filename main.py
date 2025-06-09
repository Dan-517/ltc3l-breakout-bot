from datetime import datetime, timedelta
import csv
import os
import requests
from flask import Flask, send_file
from threading import Thread
import threading
import time

# === 1. CONFIG Y MÓDULO DE DATOS & LOGGING ===

API_KEY = os.environ.get("PIONEX_API_KEY")
API_SECRET = os.environ.get("PIONEX_API_SECRET")

# Símbolo correcto en Pionex para SOL/USDT
SYMBOL = "SOLUSDT"
INTERVAL = "60M"            # Velas de 1 hora
LOOKBACK = 20               # Últimas 20 velas para High/Low
EMA_PERIOD = 200            # EMA de 200 periodos
ATR_PERIOD = 14             # ATR de 14 periodos
VOLUME_MULTIPLIER = 1.2     # Volumen_actual ≥ promedio_20h * 1.2
ATR_SL_MULT = 0.5           # Stop-loss = Low_N – ATR_14 * 0.5
ATR_TP_MULT = 2.0           # Take-profit = price + ATR_14 * 2.0
RISK_PERCENT = 0.01         # Riesgo 1% del balance por operación

LOG_FILE = "data_log.csv"
TRADES_LOG_FILE = "trades_log.csv"
ERRORS_LOG = "errors.log"

# === 2. AUTO-PING INTERNO PARA KEEP-ALIVE ===

SELF_URL = os.environ.get("SELF_URL")           # p.ej. https://mi-app.onrender.com/
PING_INTERVAL = int(os.environ.get("PING_INTERVAL", "300"))  # en segundos

def self_ping_loop():
    if not SELF_URL:
        print("⚠️ SELF_URL no definido: omitiendo self-ping interno.", flush=True)
        return
    while True:
        try:
            resp = requests.get(SELF_URL, timeout=5)
            print(f"🔔 Self-ping {SELF_URL} | status_code={resp.status_code}", flush=True)
        except Exception as e:
            print(f"⚠️ Error en self-ping: {e}", flush=True)
        time.sleep(PING_INTERVAL)

def start_self_ping_thread():
    t = threading.Thread(target=self_ping_loop, daemon=True)
    t.start()

# === 3. FLASK SETUP ===

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot de Breakout SOL/USDT activo."

@app.route("/download/data")
def download_data():
    return send_file(LOG_FILE, as_attachment=True)

@app.route("/download/trades")
def download_trades():
    return send_file(TRADES_LOG_FILE, as_attachment=True)

# === 4. FUNCIONES AUXILIARES ===

def fetch_klines(symbol, interval, limit=210):
    try:
        url = f"https://api.pionex.com/api/v1/market/klines?symbol={symbol}&interval={interval}&limit={limit}"
        response = requests.get(url, timeout=10)
        data = response.json()
        if data.get("result") and "klines" in data["data"]:
            return data["data"]["klines"]
        raise ValueError(f"fetch_klines: JSON inesperado: {data}")
    except Exception as e:
        with open(ERRORS_LOG, "a") as ef:
            ef.write(f"{datetime.utcnow().isoformat()} - ERROR fetch_klines: {e}\n")
        return None

def log_price_entry(timestamp, symbol, price, High_N, Low_N, ATR_14, vol_now, vol_avg):
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, symbol,
                         f"{price:.8f}", f"{High_N:.8f}", f"{Low_N:.8f}",
                         f"{ATR_14:.8f}", f"{vol_now:.8f}", f"{vol_avg:.8f}"])
    print(f"[{timestamp}] LOG_PRICE: {symbol} @ {price:.8f} | High_N={High_N:.8f}, Low_N={Low_N:.8f}, ATR_14={ATR_14:.8f}, Vol={vol_now:.2f}/{vol_avg:.2f}", flush=True)

def write_trade(action, symbol, price, size, sl, tp,
                usdt_pre, sol_pre, usdt_post, sol_post, pnl):
    with open(TRADES_LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([datetime.utcnow().isoformat(), action, symbol,
                         f"{price:.8f}", f"{size:.8f}",
                         f"{sl:.8f}", f"{tp:.8f}",
                         f"{usdt_pre:.8f}", f"{sol_pre:.8f}",
                         f"{usdt_post:.8f}", f"{sol_post:.8f}",
                         f"{pnl:.8f}"])
    print(f"💰 TRADE {action}: {symbol} size={size:.8f} @ {price:.8f} | SL={sl:.8f}, TP={tp:.8f}, PnL={pnl:.8f}", flush=True)

def calculate_EMA(closes, period):
    sma = sum(closes[:period]) / period
    ema = sma
    alpha = 2 / (period + 1)
    for price in closes[period:]:
        ema = alpha * price + (1 - alpha) * ema
    return ema

def calculate_ATR(klines, period):
    tr_list = []
    highs = [float(k["high"]) for k in klines]
    lows = [float(k["low"]) for k in klines]
    closes = [float(k["close"]) for k in klines]
    for i in range(-period, 0):
        prev_close = closes[i - 1]
        h = highs[i]; l = lows[i]
        tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        tr_list.append(tr)
    return sum(tr_list) / period

# === 5. ESTRATEGIA DE BREAKOUT ===

balance_usdt = 1000.0
balance_sol = 0.0
open_position = False
entry_price = 0.0
entry_size = 0.0
stop_loss = 0.0
take_profit = 0.0

def strategy_breakout():
    global balance_usdt, balance_sol, open_position, entry_price, entry_size, stop_loss, take_profit

    klines = fetch_klines(SYMBOL, INTERVAL)
    if not klines or len(klines) < EMA_PERIOD + 1:
        print("⚠️ strategy_breakout: No hay suficientes velas para indicadores.", flush=True)
        return

    closes = [float(k["close"]) for k in klines]
    highs = [float(k["high"]) for k in klines]
    lows = [float(k["low"]) for k in klines]
    volumes = [float(k["volume"]) for k in klines]

    wnd_h = highs[-LOOKBACK-1:-1]; wnd_l = lows[-LOOKBACK-1:-1]
    High_N = max(wnd_h); Low_N = min(wnd_l)

    vol_now = volumes[-1]; vol_avg = sum(volumes[-LOOKBACK-1:-1]) / LOOKBACK
    ATR_14 = calculate_ATR(klines[-(ATR_PERIOD+1):], ATR_PERIOD)

    closes_for_ema = closes[-(EMA_PERIOD+10):] if len(closes) >= EMA_PERIOD+10 else closes[-EMA_PERIOD:]
    EMA_200 = calculate_EMA(closes_for_ema, EMA_PERIOD)

    price_now = closes[-1]
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    log_price_entry(ts, SYMBOL, price_now, High_N, Low_N, ATR_14, vol_now, vol_avg)

    if not open_position:
        cond = (price_now > High_N and price_now > EMA_200 and vol_now >= vol_avg * VOLUME_MULTIPLIER)
        if cond:
            stop_loss = Low_N - ATR_14 * ATR_SL_MULT
            take_profit = price_now + ATR_14 * ATR_TP_MULT

            risk_amt = balance_usdt * RISK_PERCENT
            dist = price_now - stop_loss
            if dist <= 0:
                print("⚠️ dist ≤ 0, no abro posición.", flush=True); return
            size = risk_amt / dist

            usdt_pre, sol_pre = balance_usdt, balance_sol
            balance_sol = size; balance_usdt = 0.0
            entry_price = price_now; entry_size = size; open_position = True

            write_trade("BUY", SYMBOL, price_now, size, stop_loss, take_profit,
                        usdt_pre, sol_pre, balance_usdt, balance_sol, 0.0)
        else:
            print(f"🔍 [{ts}] Sin entrada. price={price_now:.4f}, High_N={High_N:.4f}, EMA200={EMA_200:.4f}, vol={vol_now:.2f}/{vol_avg:.2f}", flush=True)
    else:
        usdt_pre, sol_pre = balance_usdt, balance_sol
        if price_now <= stop_loss:
            pnl = (price_now - entry_price) * entry_size
            balance_usdt = entry_size * price_now; balance_sol = 0.0; open_position = False
            write_trade("SELL", SYMBOL, price_now, entry_size, stop_loss, take_profit,
                        usdt_pre, sol_pre, balance_usdt, balance_sol, pnl)
        elif price_now >= take_profit:
            pnl = (price_now - entry_price) * entry_size
            balance_usdt = entry_size * price_now; balance_sol = 0.0; open_position = False
            write_trade("SELL", SYMBOL, price_now, entry_size, stop_loss, take_profit,
                        usdt_pre, sol_pre, balance_usdt, balance_sol, pnl)
        else:
            if price_now >= entry_price + ATR_14:
                new_sl = price_now - ATR_14 * 0.75
                if new_sl > stop_loss:
                    stop_loss = new_sl
                    print(f"🔄 [TRAILING] SL→{stop_loss:.4f}", flush=True)
            else:
                print(f"🔒 [OPEN] price={price_now:.4f}, SL={stop_loss:.4f}, TP={take_profit:.4f}", flush=True)

# === 6. LOOP PRINCIPAL + HEARTBEAT ===

def is_top_of_hour():
    now = datetime.utcnow()
    return now.minute == 0 and now.second == 0

def start_bot():
    print("🔄 Bucle inmediato y luego cada 60s...", flush=True)
    try:
        print(f"\n======= [{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] EJECUCIÓN INICIAL =======", flush=True)
        strategy_breakout()
    except Exception as e:
        with open(ERRORS_LOG, "a") as ef: ef.write(f"{datetime.utcnow().isoformat()} - ERROR init: {e}\n")
        print(f"⚠️ ERROR init: {e}", flush=True)

    while True:
        time.sleep(60)
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        if is_top_of_hour():
            print(f"\n======= [{now}] HORA COMPLETA =======", flush=True)
            try:
                strategy_breakout()
            except Exception as e:
                with open(ERRORS_LOG, "a") as ef: ef.write(f"{datetime.utcnow().isoformat()} - ERROR hourly: {e}\n")
                print(f"⚠️ ERROR hourly: {e}", flush=True)
        else:
            print(f"[{now}] 💓 Bot vivo (esperando hora completa)", flush=True)

if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as f:
            csv.writer(f).writerow(["timestamp","symbol","price","High_N","Low_N","ATR_14","vol_now","vol_avg"])
        print(f"🗎 '{LOG_FILE}' creado.", flush=True)

    if not os.path.exists(TRADES_LOG_FILE):
        with open(TRADES_LOG_FILE, "w", newline="") as f:
            csv.writer(f).writerow(["ts","action","symbol","price","size","sl","tp","usdt_pre","sol_pre","usdt_post","sol_post","pnl"])
        print(f"🗎 '{TRADES_LOG_FILE}' creado.", flush=True)

    start_self_ping_thread()  # mantiene la instancia viva
    bot_thread = Thread(target=start_bot, daemon=True)
    bot_thread.start()

    port = int(os.environ.get("PORT", 8080))
    print(f"✅ Arrancando Flask en puerto {port}", flush=True)
    app.run(host="0.0.0.0", port=port)

