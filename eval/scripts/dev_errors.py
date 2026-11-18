"""Errores de eventos en dev (nunca en test), para depurar el motor. Uso: python -m eval.scripts.dev_errors [audio|hard] [desde] [hasta]"""
import sys

from copilot.nlu.engine import Engine
from eval import metrics, run_eval

src = sys.argv[1] if len(sys.argv) > 1 else "audio"
lo, hi = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (0, 60)
rows = run_eval.load_gold("dev")
preds, _ = run_eval.run_nlu(Engine(), rows)
sh = lambda k: (k[0], k[1][:3], (k[2] or "-").split("/")[-1], (k[3] or "-").split("/")[-1])
n = 0
tot = {}
for r, p in zip(rows, preds):
    if r["source"] != src:
        continue
    g, q = metrics.event_set(r["events"]), metrics.event_set(p["events"])
    for k in (g - q).elements():
        tot[("FN", k[0], k[1][:3])] = tot.get(("FN", k[0], k[1][:3]), 0) + 1
    for k in (q - g).elements():
        tot[("FP", k[0], k[1][:3])] = tot.get(("FP", k[0], k[1][:3]), 0) + 1
    if g == q:
        continue
    n += 1
    if lo < n <= hi:
        print(f"[{r['id'][-4:]}] {r['text'][:330]}\n    FN {[sh(k) for k in (g - q).elements()]}\n    FP {[sh(k) for k in (q - g).elements()]}")
print(n, "filas con error;", sorted(tot.items(), key=lambda x: -x[1])[:28])
