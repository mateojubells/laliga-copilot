#!/usr/bin/env python3
"""Genera estadisticas.js con datos SIMULADOS de una temporada completa del FC Barcelona (38 jornadas).
NO son datos reales: sirven para probar el comentarista (tarjetas "Histórico") sin API.
Es determinista (semilla fija): siempre salen los mismos números. Uso: python3 simular_estadisticas.py
Para datos reales usa build_stats.py (API-Football)."""
import json, random, datetime

rnd = random.Random(2526)
# nombre, posición, perfil de rol, minutos aprox. de una temporada de 38 jornadas
SQUAD = [
 ("Joan García","POR",0.95),("Szczesny","POR",0.15),
 ("Koundé","DEF",0.85),("Cubarsí","DEF",0.8),("Araujo","DEF",0.6),("Íñigo Martínez","DEF",0.65),("Balde","DEF",0.7),("Eric García","DEF",0.45),("Gerard Martín","DEF",0.4),
 ("Pedri","MED",0.8),("Gavi","MED",0.55),("Frenkie de Jong","MED",0.75),("Fermín López","MED",0.6),("Casadó","MED",0.4),("Dani Olmo","MED",0.6),
 ("Lamine Yamal","DEL",0.9),("Raphinha","DEL",0.85),("Ferran Torres","DEL",0.6),("Lewandowski","DEL",0.85),("Rashford","DEL",0.5),
]
# tasas por 90 minutos: tiros, a puerta, pase clave, entradas, intercepciones, duelos, regates intentados, faltas recibidas, faltas cometidas, goles, asistencias
RATE = {
 "POR":dict(sh=0.0,pk=0.05,tk=0.0,ic=0.1,du=1.5,dr=0.0,fd=0.2,fc=0.1,g=0.0,a=0.02),
 "DEF":dict(sh=0.6,pk=0.5,tk=1.8,ic=1.3,du=9.0,dr=0.7,fd=1.0,fc=1.0,g=0.05,a=0.08),
 "MED":dict(sh=1.2,pk=1.5,tk=1.9,ic=1.0,du=9.5,dr=1.7,fd=1.5,fc=1.4,g=0.12,a=0.2),
 "DEL":dict(sh=2.6,pk=1.4,tk=0.7,ic=0.3,du=10.0,dr=3.4,fd=2.2,fc=0.8,g=0.45,a=0.25),
}
# ajustes por jugador para que el resultado "se parezca": regateadores, provocadores de penaltis, pateadores...
TWEAK = {
 "Lamine Yamal":dict(dr=2.0,fd=1.8,pen_won=6,pen_scored=2,pen_miss=0,g=0.6,a=0.4,pk=1.7),
 "Raphinha":dict(dr=1.3,g=0.55,a=0.35,pk=1.9,pen_scored=1),
 "Pedri":dict(pk=1.1,dr=1.4,fd=1.3,g=0.05),
 "Gavi":dict(fc=2.1,fd=1.8,yc_boost=1.7),
 "Lewandowski":dict(g=0.65,pen_scored=7,pen_miss=1,dr=0.4,pen_won=1,fd=1.4),
 "Araujo":dict(fc=1.7,yc_boost=1.6,red=1,pen_comm=2),
 "Balde":dict(dr=1.8,fd=1.5),
 "Ferran Torres":dict(g=0.5,pen_won=2),
 "Fermín López":dict(g=0.3,dr=1.0),
 "Rashford":dict(dr=2.0,g=0.35,a=0.25),
 "Joan García":dict(saves=2.6),
 "Szczesny":dict(saves=2.4),
 "Íñigo Martínez":dict(pen_comm=1),
 "Casadó":dict(tk=1.0,fc=0.9),
}

def jitter(x, spread=0.2):
    return x * rnd.uniform(1 - spread, 1 + spread)

players = []
for name, pos, share in SQUAD:
    r = dict(RATE[pos]); tw = TWEAK.get(name, {})
    for k in r:
        if k in tw: r[k] = tw[k]                       # el ajuste del jugador sustituye a la tasa de su posición
    minutes = int(jitter(38 * 90 * share, 0.08))
    games = max(1, round(minutes / (90 if pos != "POR" else 90) * (1.15 if pos != "POR" else 1.0)))
    games = min(38, games); p90 = minutes / 90
    def c(rate): return max(0, int(round(jitter(rate * p90, 0.18))))
    dribbles = c(r["dr"]); ok = int(round(dribbles * rnd.uniform(0.5, 0.65)))
    shots = c(r["sh"]); on = int(round(shots * rnd.uniform(0.35, 0.5)))
    goals = c(r["g"]); fouls_c = c(r["fc"])
    yellow = int(round(fouls_c * rnd.uniform(0.1, 0.2) * tw.get("yc_boost", 1.0)))
    s = {"games": games, "minutes": minutes, "goals": goals, "assists": c(r["a"]),
         "saves": c(tw["saves"]) if "saves" in tw else 0,
         "shots": shots, "shots_on": on, "key_passes": c(r["pk"]),
         "tackles": c(r["tk"]), "interceptions": c(r["ic"]),
         "duels": c(r["du"]), "dribbles": dribbles, "dribbles_ok": ok, "dribbled_past": c(1.0 if pos in ("DEF", "MED") else 0.4),
         "fouls_drawn": c(r["fd"]), "fouls_committed": fouls_c,
         "yellow": yellow, "yellowred": 0, "red": tw.get("red", 0),
         "pen_won": tw.get("pen_won", 0), "pen_committed": tw.get("pen_comm", 0),
         "pen_scored": tw.get("pen_scored", 0), "pen_missed": tw.get("pen_miss", 0), "pen_saved": 0}
    s["duels_won"] = int(round(s["duels"] * rnd.uniform(0.48, 0.58)))
    if name == "Szczesny": s["pen_saved"] = 1
    if name == "Joan García": s["pen_saved"] = 2
    s["goals"] = max(s["goals"], s["pen_scored"])
    players.append({"n": name, "a": name, "t": "FC Barcelona", "s": s})

data = {"season": "SIMULADA (38 jornadas)", "built": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "DATOS SIMULADOS, NO REALES", "players": players}
with open("estadisticas.js", "w", encoding="utf-8") as f:
    f.write("/* DATOS SIMULADOS del FC Barcelona para probar el comentarista. No son reales. Generado con simular_estadisticas.py */\n")
    f.write("window.PSTATS = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n")
print("estadisticas.js: %d jugadores simulados" % len(players))
for p in players:
    s = p["s"]; print("%-16s PJ%2d %4d min  G%2d A%2d  regates %3d/%3d  FR%3d FC%3d  pen: prov %d com %d marc %d fall %d  amar %d" % (
        p["n"], s["games"], s["minutes"], s["goals"], s["assists"], s["dribbles_ok"], s["dribbles"], s["fouls_drawn"], s["fouls_committed"],
        s["pen_won"], s["pen_committed"], s["pen_scored"], s["pen_missed"], s["yellow"]))
