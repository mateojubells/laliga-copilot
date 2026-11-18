"""Comprobación de extremo a extremo con voz EN VIVO: servidor real + motor de voz a velocidad real sobre un tramo
del audio. Uso: python -m eval.scripts.live_voice_check [desde] [hasta]. Imprime transcripción, eventos y tarjetas."""
import json
import sys
import time

from fastapi.testclient import TestClient

from copilot.server.app import app

start, until = (float(sys.argv[1]), float(sys.argv[2])) if len(sys.argv) > 2 else (1193.0, 1262.0)
with TestClient(app) as c:
    c.app.state.session.auto_program = True
    with c.websocket_connect("/ws?role=operator") as ws:
        ws.send_text(json.dumps({"type": "replay_control", "value": "start", "event": {"from": start, "until": until, "mode": "voz"}}))
        t0 = time.time()
        seen_start = None
        while time.time() - t0 < (until - start) + 60:
            m = json.loads(ws.receive_text())
            if m["type"] == "status" and (m.get("data") or {}).get("replay_started"):
                seen_start = time.time()
                print("motor:", m["data"].get("asr"))
            elif m["type"] == "transcript" and m["transcript"]["final"]:
                tr = m["transcript"]
                print(f"  [{tr['t0']:7.1f}-{tr['t1']:7.1f}] +{(time.time() - seen_start) - (tr['t1'] - start):4.1f}s  {tr['text'][:110]}")
            elif m["type"] == "event" and m["event"].get("action") in ("new", "update", "retract"):
                e = m["event"]
                print(f"  EVENTO {e['action']} {e['type']} {e['roles']} (audio {e['t_audio']:.1f}, reloj +{time.time() - seen_start + start - e['t_audio']:.1f}s)")
            elif m["type"] == "graphic":
                g = m["graphic"]
                print(f"  TARJETA {g['kind']} {g['state']} parcial={bool(g['ts'].get('partial'))} · {g['reason'].get('text', '')[:60]}")
            elif m["type"] == "status" and seen_start and (m.get("data") or {}).get("replay") is None:
                break
    print(json.dumps(c.get("/api/metrics").json()["status"], ensure_ascii=False))
