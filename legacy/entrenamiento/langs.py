#!/usr/bin/env python3
"""Detecta el idioma del comentario de cada partido (heurística de palabras funcionales). Escribe echoes/game_lang.json
Uso: python3 langs.py DIRECTORIO     (necesita pyarrow)"""
import pyarrow as pa, collections, re, json, sys
S = sys.argv[1]
t = pa.ipc.open_stream(open(S + "/echoes/soccer_net_echoes_hf_dataset-train.arrow", "rb")).read_all()
W = {"es": set("el la los las de que y en con pero un una es por para lo se su al del muy más como ya hay está pues también aquí ahora bien".split()),
     "en": set("the and of to in is it that with but he they his on for this was are at ball a".split()),
     "de": set("der die das und ist nicht ein eine mit den von zu auch auf sich".split()),
     "fr": set("le la les des et est un une pour dans qui sur pas au ce".split()),
     "it": set("il lo gli di che è un una per con non sono della nel".split())}
sc = collections.defaultdict(collections.Counter)
for gi, x in zip(t.column("game").to_pylist(), t.column("text").to_pylist()):
    gm = gi.rsplit("/", 1)[0]
    for w in re.findall(r"[a-záéíóúñüàèìòùäöß']+", x.lower()):
        for l, s in W.items():
            if w in s: sc[gm][l] += 1
json.dump({gm: (max(c, key=c.get) if c else "?") for gm, c in sc.items()}, open(S + "/echoes/game_lang.json", "w"))
