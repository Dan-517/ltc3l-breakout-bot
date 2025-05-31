import os
import time
import requests
from flask import Flask
from threading import Thread

ASSET = "litecoin"
TRADE_PAIR = "LTC3L/USDT"
INVEST_AMOUNT = 11
TP_PERCENT = 0.10
SL_PERCENT = 0.05

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running."

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

def get_price(asset=ASSET):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={asset}&vs_currencies=usd"
        r = requests.get(url).json()
        return r[asset]["usd"]
    except Exception as e:
        print("Error getting price:", e)
        return None

def monitor_and_trade():
    print("="*50)
    print("🔁 Bot started. Monitoring market every 10 minutes.")
    print(f"🔍 Watching {ASSET.upper()}, trading {TRADE_PAIR}, with ${INVEST_AMOUNT} per breakout.")
    print("="*50)

    prices = []
    while True:
        price = get_price()
        now = time.strftime('%Y-%m-%d %H:%M:%S')

        if price:
            prices.append(price)
            if len(prices) > 6:
                prices.pop(0)
            print(f"[{now}] Price: ${price:.2f}")

            if len(prices) == 6:
                change = (price - prices[0]) / prices[0]
                print(f"📈 1h change: {change * 100:.2f}%")

                if change >= 0.06:
                    simulate_trade(price)
                    prices.clear()
                else:
                    print("📉 No breakout. Holding...")
        else:
            print("⚠️ Could not fetch price.")

        print("-" * 50)
        time.sleep(600)

def simulate_trade(entry_price):
    tp = entry_price * (1 + TP_PERCENT)
    sl = entry_price * (1 - SL_PERCENT)
    print("="*40)
    print(f"🚀 SIMULATED TRADE ENTERED")
    print(f"🕒 {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"💵 Entry Price: ${entry_price:.2f}")
    print(f"🎯 Take Profit: ${tp:.2f}")
    print(f"🛑 Stop Loss: ${sl:.2f}")
    print(f"📊 Simulating with ${INVEST_AMOUNT} on {TRADE_PAIR}")
    print("="*40)

keep_alive()
monitor_and_trade()
