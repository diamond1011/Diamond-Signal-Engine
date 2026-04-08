import requests
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

TG_TOKEN = "8563359700:AAF2lOkal_iDOSMhyndVDsPNvKfIa1x0QaE"
TG_CHAT = "5106454697"
BIAS_MIN = 0.65
INTERVAL = 3600

ASSETS = [
    {"id": "BTC", "sym": "BTC_USDT"},
    {"id": "GOLD", "sym": "XAUT_USDT"},
    {"id": "SILVER", "sym": "SILVER_USDT"},
    {"id": "OIL", "sym": "USOIL_USDT"},
]

sent = {}

def send_tg(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": text},
            timeout=10
        )
    except:
        pass

def get_price(sym):
    try:
        url = f"https://contract.mexc.com/api/v1/contract/ticker?symbol={sym}"
        r = requests.get(url, timeout=10).json()
        if r.get("success") and r.get("data"):
            return float(r["data"]["lastPrice"])
    except:
        pass
    return None

def get_klines(sym):
    try:
        if sym == "BTC_USDT":
            url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=200"
            r = requests.get(url, timeout=10).json()
            return [{"ret": (float(k[4])-float(k[1]))/float(k[1])} for k in r]
        url = f"https://contract.mexc.com/api/v1/contract/kline/{sym}?interval=Hour1"
        r = requests.get(url, timeout=15).json()
        if r.get("success") and r.get("data"):
            closes = r["data"].get("close", [])
            opens = r["data"].get("open", [])
            return [{"ret": (float(closes[i])-float(opens[i]))/float(opens[i])} for i in range(len(closes))]
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

def check_signals():
    windows = [
        {"label": "12H", "size": 12},
        {"label": "24H", "size": 24},
        {"label": "48H", "size": 48},
        {"label": "1W", "size": 168},
    ]
    for asset in ASSETS:
        candles = get_klines(asset["sym"])
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
                        f"https://diamondsignalengine.netlify.app"
                    )
                    send_tg(msg)
                    time.sleep(0)

# Proxy HTTP server
prices_cache = {}

class ProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/price/"):
            sym = self.path.split("/price/")[1]
            price = get_price(sym)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            if price:
                self.wfile.write(json.dumps({"success": True, "price": price}).encode())
            else:
                self.wfile.write(json.dumps({"success": False}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

def run_server():
    server = HTTPServer(("0.0.0.0", 8080), ProxyHandler)
    server.serve_forever()

def main():
    send_tg("🤖 Bot activo 24/7\nProxy de precios MEXC activado.")
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    while True:
        try:
            check_signals()
        except Exception as e:
            pass
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
