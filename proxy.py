#!/usr/bin/env python3
"""
Delta Neutral Dashboard — Proxy + Static Server
Deploy-ready: sirve el dashboard HTML + API de datos.
Compatible con Render.com (lee PORT del entorno).
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import ssl
import json
import time
import threading
import os

# ─── CONFIG ───────────────────────────────────────────────────────
PORT = int(os.environ.get("PORT", 8765))
HIBACHI_URL = "https://data-api.hibachi.xyz/market/inventory"
HYPERLIQUID_URL = "https://api.hyperliquid.xyz/info"
HYENA_DEX = "hyna"

HYENA_REFRESH = 2
HIBACHI_REFRESH = 6

# ─── CACHE ────────────────────────────────────────────────────────
CACHE = {
    "hyena": {},
    "hibachi": {},
    "hyena_timestamp": 0,
    "hibachi_timestamp": 0
}

# ─── DASHBOARD HTML (cargado al inicio) ──────────────────────────
DASHBOARD_HTML = b""
def load_dashboard():
    global DASHBOARD_HTML
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    if os.path.exists(html_path):
        with open(html_path, "rb") as f:
            DASHBOARD_HTML = f.read()
        print(f"📄 Dashboard cargado: {len(DASHBOARD_HTML)} bytes")
    else:
        DASHBOARD_HTML = b"<h1>index.html no encontrado</h1>"
        print("⚠️  index.html no encontrado junto a proxy.py")

# ─── DATA FETCHERS ───────────────────────────────────────────────
def fetch_hyena():
    try:
        req = urllib.request.Request(
            HYPERLIQUID_URL,
            data=json.dumps({"type": "metaAndAssetCtxs", "dex": HYENA_DEX}).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            meta, ctxs = json.load(resp)

        result = {}
        for i, asset in enumerate(meta.get('universe', [])):
            full_name = asset.get('name')
            if not full_name or i >= len(ctxs):
                continue
            sym = full_name.split(':')[1] if ':' in full_name else full_name
            px = float(ctxs[i].get('markPx', 0))
            fund = float(ctxs[i].get('funding', 0)) * 100
            result[sym] = {"px": px, "fund": fund}
        return result, len(result)
    except Exception as e:
        print(f"❌ HyENA error: {e}")
        return {}, 0

def fetch_hibachi():
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(
            HIBACHI_URL,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            raw = json.load(resp)
            markets = raw.get('markets', raw.get('data', []))
            result = {}
            for m in markets:
                contract = m.get('contract', {})
                info = m.get('info', {})
                sym_raw = contract.get('underlyingSymbol') or contract.get('symbol') or ''
                sym = sym_raw.upper().split('/')[0].split('-')[0]
                px = float(info.get('markPrice') or info.get('priceLatest') or 0)
                fund = float(info.get('estimatedFundingRate') or 0)
                if abs(fund) < 0.1 and fund != 0:
                    fund *= 100
                if sym and px > 0:
                    result[sym] = {"px": px, "fund": fund}
            return result, len(result)
    except Exception as e:
        print(f"❌ Hibachi error: {e}")
        return {}, 0

# ─── BACKGROUND WORKERS ─────────────────────────────────────────
def hyena_worker():
    global CACHE
    print(f"🟣 Worker HyENA iniciado (cada {HYENA_REFRESH}s)")
    while True:
        try:
            data, count = fetch_hyena()
            if data:
                CACHE["hyena"] = data
                CACHE["hyena_timestamp"] = time.time()
        except Exception as e:
            print(f"❌ HyENA worker: {e}")
        time.sleep(HYENA_REFRESH)

def hibachi_worker():
    global CACHE
    print(f"🔵 Worker Hibachi iniciado (cada {HIBACHI_REFRESH}s)")
    while True:
        try:
            data, count = fetch_hibachi()
            if data:
                CACHE["hibachi"] = data
                CACHE["hibachi_timestamp"] = time.time()
        except Exception as e:
            print(f"❌ Hibachi worker: {e}")
        time.sleep(HIBACHI_REFRESH)

# ─── HTTP HANDLER ────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/api/data":
            # Endpoint de datos (JSON)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            response = {
                "hyena": CACHE["hyena"],
                "hibachi": CACHE["hibachi"],
                "hyena_timestamp": CACHE["hyena_timestamp"],
                "hibachi_timestamp": CACHE["hibachi_timestamp"]
            }
            self.wfile.write(json.dumps(response).encode())

        elif self.path == "/api/health":
            # Health check para Render
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "hyena_pairs": len(CACHE["hyena"]),
                "hibachi_pairs": len(CACHE["hibachi"]),
                "uptime": time.time()
            }).encode())

        else:
            # Cualquier otra ruta → servir el dashboard
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt, *args):
        # Solo loguear errores, no cada request
        if args and '404' in str(args[0]):
            super().log_message(fmt, *args)

# ─── MAIN ────────────────────────────────────────────────────────
if __name__ == "__main__":
    load_dashboard()

    threading.Thread(target=hyena_worker, daemon=True).start()
    threading.Thread(target=hibachi_worker, daemon=True).start()

    print("=" * 50)
    print(f"🚀 SERVIDOR: http://0.0.0.0:{PORT}")
    print(f"   Dashboard: http://0.0.0.0:{PORT}/")
    print(f"   API datos: http://0.0.0.0:{PORT}/api/data")
    print(f"   Health:    http://0.0.0.0:{PORT}/api/health")
    print(f"🟣 HyENA: cada {HYENA_REFRESH}s")
    print(f"🔵 Hibachi: cada {HIBACHI_REFRESH}s")
    print("=" * 50 + "\n")

    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
