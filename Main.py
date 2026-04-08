import requests
import time
import math

TG_TOKEN = "8563359700:AAF2lOkal_iDOSMhyndVDsPNvKfIa1b0QaE"
TG_CHAT = "5106454697"
PROXY = "https://corsproxy.io/?"
BIAS_MIN = 0.65
INTERVAL = 3600  # cada hora

ASSETS = [
    {"id": "BTC", "sym": "BTC_USDT", "dec": 1},
    {"id": "GOLD", "sym": "XAUT_USDT", "dec": 2},
    {"id": "SILVER", "sym": "SILVER_USDT", "dec": 3},
    {"id": "OIL", "sym": "USOIL_USDT", "dec": 2},
]

sent = {}

def send_tg(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": text}
        )
    except:
        pass

def get_price(sym):
    try:
        url = PROXY + f"https://contract.mexc.com/api/v1/contract/ticker?symbol={sym}"
        r = requests.get(url, timeout=10).json()
        if r.get("success") and r.get("data"):
            return float(r["data"]["lastPrice"])
    except:
        pass
    return None

def get_klines(sym):
    try:
        url = PROXY + f"https://contract.mexc.com/api/v1/contract/kline/{sym}?interval=Hour1&start=0&end=0"
        r = requests.get(url, timeout=15).json()
        if r.get("success") and r.get("data"):
            d = r["data"]
            closes = d.get("close", [])
            opens = d.get("open", [])
            highs = d.get("high", [])
            lows = d.get("low", [])
            candles = []
            for i in range(len(closes)):
                o = float(opens[i]) if i < len(opens) else float(closes[i])
                c = float(closes[i])
                h = float(highs[i]) if i < len(highs) else max(o,c)
                l = float(lows[i]) if i < len(lows) else min(o,c)
                ret = (c - o) / o if o else 0
                candles.append({"o":o,"h":h,"l":l,"c":c,"ret":ret})
            return candles
    except:
        pass
    return []

def analyze(candles, window):
    if len(candles) < window:
        return None
    sl = candles[-window:]
    ups = sum(1 for c in sl if c["ret"] > 0)
    n = len(sl)
    wins = ups / n
    bias = wins if wins > 0.5 else 1 - wins
    direction = "LONG" if wins >= 0.5 else "SHORT"
    return {"bias": bias, "dir": direction}

def check():
    windows = [
        {"label": "12H", "size": 12},
        {"label": "24H", "size": 24},
        {"label": "48H", "size": 48},
        {"label": "1W", "size": 168},
    ]
    for asset in ASSETS:
        candles = get_klines(asset["sym"])
        if not candles:
            # fallback Binance for BTC
            if asset["id"] == "BTC":
                try:
                    url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=200"
                    r = requests.get(url, timeout=10).json()
                    candles = [{"o":float(k[1]),"h":float(k[2]),"l":float(k[3]),"c":float(k[4]),"ret":(float(k[4])-float(k[1]))/float(k[1])} for k in r]
                except:
                    pass
        if not candles:
            continue
        price = get_price(asset["sym"])
        for w in windows:
            result = analyze(candles, w["size"])
            if not result:
                continue
            if result["bias"] >= BIAS_MIN:
                key = f"{asset['id']}-{w['label']}-{result['dir']}"
                if key not in sent:
                    sent[key] = True
                    msg = (
                        f"🚨 SEÑAL — {asset['id']}\n"
                        f"{'🟢 LONG' if result['dir'] == 'LONG' else '🔴 SHORT'} {w['label']}\n"
                        f"Bias: {result['bias']*100:.1f}%\n"
                        f"Precio MEXC: {price}\n\n"
                        f"Abre la app para ver niveles:\n"
                        f"https://diamondsignalengine.netlify.app"
                    )
                    send_tg(msg)
                    # Reset after 1 hour
                    time.sleep(0)

def main():
    send_tg("🤖 Bot de señales activo 24/7\nRecibirás alertas automáticas aunque no tengas la app abierta.")
    while True:
        try:
            check()
        except Exception as e:
            pass
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
