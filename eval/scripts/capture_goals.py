"""Secuencia de capturas del modo repetición en los goles: con el servidor real en marcha, reproduce el tramo de cada
gol (transcripción de referencia, modo automático) y captura la SALIDA DE PROGRAMA cuando el grafismo está en antena.
Uso: python -m eval.scripts.capture_goals   (necesita backend en :8765, Vite en :5173 y Chrome)."""
import asyncio
import base64
import json
import subprocess
import time
import urllib.request
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[2]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = ROOT / "docs" / "screens" / "replay"
GOALS = [("1-0_raphinha_20", 1193, 1262), ("2-0_lewandowski_24", 1415, 1475), ("3-0_kounde_45+2", 2815, 2865)]
PORT = 9333


async def shot(cdp, path: Path) -> None:
    await cdp.send(json.dumps({"id": 1, "method": "Page.captureScreenshot", "params": {"format": "png"}}))
    while True:
        m = json.loads(await cdp.recv())
        if m.get("id") == 1:
            path.write_bytes(base64.b64decode(m["result"]["data"]))
            return


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    chrome = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1920,1080",
                               f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/claude-501/chrome-capture",
                               "http://localhost:5173/program?bg=green&scale=1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json").read())
                page = next(t for t in tabs if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.5)
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=None) as cdp:
            await cdp.send(json.dumps({"id": 7, "method": "Emulation.setDeviceMetricsOverride",
                                       "params": {"width": 1920, "height": 1080, "deviceScaleFactor": 1, "mobile": False}}))
            for name, a, b in GOALS:
              async with websockets.connect("ws://127.0.0.1:8765/ws?role=operator") as ws:
                await ws.send(json.dumps({"type": "set_auto", "value": True}))
                await ws.send(json.dumps({"type": "clear_program"}))
                await ws.send(json.dumps({"type": "replay_control", "value": "start", "event": {"from": a, "until": b, "speed": 6}}))
                started, t0 = False, time.time()
                while time.time() - t0 < 60:
                    m = json.loads(await asyncio.wait_for(ws.recv(), 60))
                    if m["type"] == "status" and (m.get("data") or {}).get("replay_started"):
                        started = True
                    elif m["type"] == "program" and started:
                        g = m["graphic"]
                        print(name, "→", g["kind"], "·", g["reason"].get("text", "")[:70])
                        await asyncio.sleep(1.5)  # animación de entrada
                        await shot(cdp, OUT / f"{name}.png")
                        break
                await ws.send(json.dumps({"type": "replay_control", "value": "stop"}))
                await asyncio.sleep(0.5)
    finally:
        chrome.terminate()

if __name__ == "__main__":
    asyncio.run(main())
