#!/usr/bin/env python3
"""
Delta Neutral Terminal — Proxy para Render
Sirve HTML en / y API JSON en /api
Workers separados: HyENA (2s), Hibachi (6s)
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import ssl
import json
import time
import threading
import os

PORT = int(os.environ.get("PORT", 8765))
HIBACHI_URL = "https://data-api.hibachi.xyz/market/inventory"
HYPERLIQUID_URL = "https://api.hyperliquid.xyz/info"
HYENA_DEX = "hyna"

HYENA_REFRESH = 2
HIBACHI_REFRESH = 6

CACHE = {
    "hyena": {},
    "hibachi": {},
    "hyena_timestamp": 0,
    "hibachi_timestamp": 0
}

# ─── WALLET STATE ─────────────────────────────────────
WALLET = {
    "address": None,
    "connected": False,
    "positions": {"hl": [], "hyena": []},
    "account": {"hl": {}, "hyena": {}}
}

# ─── HTML (se carga una vez al arrancar) ──────────────
HTML_CONTENT = b""

def load_html():
    global HTML_CONTENT
    # Buscar el HTML en el mismo directorio que proxy.py
    script_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(script_dir, "index.html")
    
    if os.path.exists(html_path):
        with open(html_path, "rb") as f:
            HTML_CONTENT = f.read()
        print(f"✅ HTML cargado: {html_path} ({len(HTML_CONTENT)} bytes)")
    else:
        HTML_CONTENT = b"<h1>index.html no encontrado</h1>"
        print(f"❌ No se encontro index.html en {script_dir}")

# ─── WORKERS ──────────────────────────────────────────
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

def fetch_wallet_positions(address):
    """Consulta posiciones abiertas en Hyperliquid (HL + HyENA)"""
    result = {"hl": [], "hyena": [], "account": {"hl": {}, "hyena": {}}}
    
    for dex_name, dex_param in [("hl", None), ("hyena", HYENA_DEX)]:
        try:
            payload = {"type": "clearinghouseState", "user": address}
            if dex_param:
                payload["dex"] = dex_param
            
            req = urllib.request.Request(
                HYPERLIQUID_URL,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.load(resp)
            
            # Account value
            margin_summary = data.get("marginSummary") or data.get("crossMarginSummary", {})
            acc_val = float(margin_summary.get("accountValue", 0))
            result["account"][dex_name] = {"accountValue": acc_val}
            
            # Positions
            positions = data.get("assetPositions", [])
            for p in positions:
                pos = p.get("position", p)
                coin = pos.get("coin", "")
                if ":" in coin:
                    coin = coin.split(":")[1]
                szi = float(pos.get("szi", 0))
                if szi == 0:
                    continue
                entry_px = float(pos.get("entryPx", 0))
                lev_info = pos.get("leverage", {})
                lev_val = float(lev_info.get("value", 1)) if isinstance(lev_info, dict) else float(lev_info or 1)
                margin_used = float(pos.get("marginUsed", 0))
                
                result[dex_name].append({
                    "coin": coin,
                    "side": "short" if szi < 0 else "long",
                    "size": abs(szi),
                    "entryPx": entry_px,
                    "leverage": lev_val,
                    "marginUsed": margin_used
                })
        except Exception as e:
            print(f"❌ Wallet {dex_name} error: {e}")
    
    return result

def hyena_worker():
    global CACHE
    print(f"🟣 Worker HyENA iniciado (cada {HYENA_REFRESH}s)")
    while True:
        try:
            data, count = fetch_hyena()
            if data:
                CACHE["hyena"] = data
                CACHE["hyena_timestamp"] = time.time()
                print(f"✅ HyENA: {count} pares [{time.strftime('%H:%M:%S')}]")
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
                print(f"✅ Hibachi: {count} pares [{time.strftime('%H:%M:%S')}]")
        except Exception as e:
            print(f"❌ Hibachi worker: {e}")
        time.sleep(HIBACHI_REFRESH)

def wallet_worker():
    """Actualiza posiciones del wallet cada 10s si está conectado"""
    global WALLET
    print("👛 Worker Wallet iniciado (cada 10s si conectado)")
    while True:
        if WALLET["connected"] and WALLET["address"]:
            try:
                pos_data = fetch_wallet_positions(WALLET["address"])
                WALLET["positions"] = {"hl": pos_data["hl"], "hyena": pos_data["hyena"]}
                WALLET["account"] = pos_data["account"]
            except Exception as e:
                print(f"❌ Wallet worker: {e}")
        time.sleep(10)

# ─── HTTP HANDLER ─────────────────────────────────────
class ProxyHandler(BaseHTTPRequestHandler):
    
    def do_GET(self):
        if self.path == "/api" or self.path == "/api/":
            # Servir datos JSON
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            
            response = {
                "hyena": CACHE["hyena"],
                "hibachi": CACHE["hibachi"],
                "hyena_timestamp": CACHE["hyena_timestamp"],
                "hibachi_timestamp": CACHE["hibachi_timestamp"]
            }
            
            # Incluir datos de wallet si está conectado
            if WALLET["connected"]:
                response["positions"] = {
                    "connected": True,
                    "wallet": WALLET["address"][:6] + "…" + WALLET["address"][-4:] if WALLET["address"] else "",
                    "hl": WALLET["positions"].get("hl", []),
                    "hyena": WALLET["positions"].get("hyena", []),
                    "account": WALLET["account"]
                }
            
            self.wfile.write(json.dumps(response).encode())
        
        else:
            # Servir HTML (cualquier otra ruta)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(HTML_CONTENT)
    
    def do_POST(self):
        if self.path == "/api" or self.path == "/api/":
            content_len = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_len)) if content_len > 0 else {}
            
            action = body.get("action", "")
            result = {"ok": False}
            
            if action == "set_wallet":
                addr = body.get("address", "").strip()
                if addr and addr.startswith("0x") and len(addr) == 42:
                    WALLET["address"] = addr
                    WALLET["connected"] = True
                    short_addr = addr[:6] + "…" + addr[-4:]
                    result = {"ok": True, "wallet": short_addr}
                    print(f"👛 Wallet conectada: {short_addr}")
                else:
                    result = {"ok": False, "error": "Dirección inválida"}
            
            elif action == "disconnect_wallet":
                WALLET["address"] = None
                WALLET["connected"] = False
                WALLET["positions"] = {"hl": [], "hyena": []}
                WALLET["account"] = {"hl": {}, "hyena": {}}
                result = {"ok": True}
                print("👛 Wallet desconectada")
            
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    
    def log_message(self, fmt, *args):
        pass

# ─── MAIN ─────────────────────────────────────────────
if __name__ == "__main__":
    load_html()
    
    threading.Thread(target=hyena_worker, daemon=True).start()
    threading.Thread(target=hibachi_worker, daemon=True).start()
    threading.Thread(target=wallet_worker, daemon=True).start()
    
    print("=" * 50)
    print(f"🚀 SERVIDOR: http://0.0.0.0:{PORT}")
    print(f"   HTML en /  |  API en /api")
    print(f"🟣 HyENA: cada {HYENA_REFRESH}s")
    print(f"🔵 Hibachi: cada {HIBACHI_REFRESH}s")
    print(f"👛 Wallet: cada 10s (si conectada)")
    print("=" * 50 + "\n")
    
    HTTPServer(("0.0.0.0", PORT), ProxyHandler).serve_forever()
