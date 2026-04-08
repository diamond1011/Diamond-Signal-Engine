import requests
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

TG_TOKEN = "8563359700:AAF2lOkal_iDOSMhyndVDsPNvKfIa1x0QaE"
TG_CHAT = "5106454697"
BIAS_MIN = 0.65
BIAS_CONTRA = 0.75
INTERVAL = 3600

ASSETS = [
    {"id": "BTC", "sym": "BTC_USDT"},
    {"id": "GOLD", "sym": "XAUT_USDT"},
    {"id": "SILVER", "sym": "SILVER_USDT"},
    {"id": "OIL", "sym": "USOIL_USDT"},
]

sent = {}
signal_history = {}  # {asset_id+window+dir: timestamp_primera_vez}
open_trades = {}     # {asset_id: {dir, window}} — se actualiza via webhook futuro

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

def format_duration(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h > 0:
        return f"{h}h {m}min"
    return f"{m}min"

def check_signals():
    windows = [
        {"label": "12H", "size": 12},
        {"label": "24H", "size": 24},
        {"label": "48H", "size": 48},
        {"label": "1W", "size": 168},
    ]
    
    now = time.time()
    asset_signals = {}  # para detectar confluencia y señales contrarias
    
    for asset in ASSETS:
        candles = get_klines(asset["sym"])
        if not candles:
            continue
        price = get_price(asset["sym"])
        asset_signals[asset["id"]] = []
        
        for w in windows:
            result = analyze(candles, w["size"])
            if not result:
                continue
                
            if result["bias"] >= BIAS_MIN:
                key = f"{asset['id']}-{w['label']}-{result['dir']}"
                
                # Registrar primera vez que apareció la señal
                if key not in signal_history:
                    signal_history[key] = now
                
                duration = now - signal_history[key]
                duration_str = format_duration(duration)
                is_new = duration < 1800  # menos de 30 minutos
                
                asset_signals[asset["id"]].append({
                    "window": w["label"],
                    "dir": result["dir"],
                    "bias": result["bias"],
                    "duration": duration_str,
                    "is_new": is_new
                })
                
                # Mandar señal nueva
                if key not in sent:
                    sent[key] = True
                    new_tag = "⚡ NUEVA" if is_new else f"⏱ {duration_str} activa"
                    msg = (
                        f"🚨 SEÑAL — {asset['id']}\n"
                        f"{'🟢 LONG' if result['dir'] == 'LONG' else '🔴 SHORT'} {w['label']}\n"
                        f"Bias: {result['bias']*100:.1f}%\n"
                        f"{new_tag}\n"
                        f"Precio MEXC: {price}\n\n"
                        f"https://diamondsignalengine.netlify.app"
                    )
                    send_tg(msg)
            else:
                # Limpiar señal si ya no está activa
                for d in ["LONG", "SHORT"]:
                    key = f"{asset['id']}-{w['label']}-{d}"
                    if key in sent:
                        del sent[key]
                    if key in signal_history:
                        del signal_history[key]
    
    # Detectar confluencia — cuando 24H y 48H o 24H y 1W coinciden
    for asset_id, sigs in asset_signals.items():
        if len(sigs) >= 2:
            dirs = [s["dir"] for s in sigs]
            windows_active = [s["window"] for s in sigs]
            if dirs.count("LONG") >= 2 or dirs.count("SHORT") >= 2:
                dominant_dir = "LONG" if dirs.count("LONG") >= 2 else "SHORT"
                if ("24H" in windows_active or "48H" in windows_active) and "1W" in windows_active:
                    conf_key = f"CONFLUENCIA-{asset_id}-{dominant_dir}"
                    if conf_key not in sent:
                        sent[conf_key] = True
                        price = get_price(next(a["sym"] for a in ASSETS if a["id"] == asset_id))
                        msg = (
                            f"🔥🔥 CONFLUENCIA FUERTE — {asset_id}\n"
                            f"{'🟢 LONG' if dominant_dir == 'LONG' else '🔴 SHORT'}\n"
                            f"Ventanas activas: {', '.join(windows_active)}\n"
                            f"Precio MEXC: {price}\n\n"
                            f"Alta probabilidad — señal confirmada en múltiples ventanas\n\n"
                            f"https://diamondsignalengine.netlify.app"
                        )
                        send_tg(msg)

    # Detectar señales contrarias fuertes a trades abiertos
    # Los trades abiertos se leen desde un archivo compartido
    try:
        with open("trades.json", "r") as f:
            trades = json.load(f)
        for trade in trades:
            if trade.get("status") != "OPEN":
                continue
            asset_id = trade["assetId"]
            trade_dir = trade["dir"]
            contra_dir = "SHORT" if trade_dir == "LONG" else "LONG"
            
            if asset_id in asset_signals:
                for sig in asset_signals[asset_id]:
                    if sig["dir"] == contra_dir and sig["bias"] >= BIAS_CONTRA:
                        contra_key = f"CONTRA-{asset_id}-{sig['window']}-{contra_dir}"
                        if contra_key not in sent:
                            sent[contra_key] = True
                            send_tg(
                                f"⚠️ SEÑAL CONTRARIA FUERTE — {asset_id}\n"
                                f"Tienes un {trade_dir} abierto\n"
                                f"Señal {contra_dir} {sig['window']} con {sig['bias']*100:.1f}% bias\n\n"
                                f"Considera cerrar tu posición\n\n"
                                f"https://diamondsignalengine.netlify.app"
                            )
    except:
        pass

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
        elif self.path == "/trades":
            try:
                with open("trades.json", "r") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data.encode())
            except:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b"[]")
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/trades":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                trades = json.loads(body)
                with open("trades.json", "w") as f:
                    json.dump(trades, f)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
            except:
                self.send_response(400)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        pass

def run_server():
    server = HTTPServer(("0.0.0.0", 8080), ProxyHandler)
    server.serve_forever()

def main():
    # send_tg("🤖 Bot activo 24/7\n✅ Proxy MEXC\n✅ Señales 24/7\n✅ Alertas confluencia\n✅ Alertas señal contraria")
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
