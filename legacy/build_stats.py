#!/usr/bin/env python3
"""Genera estadisticas.js (regates, faltas recibidas, penaltis provocados, tarjetas, tiros...) por jugador de LaLiga.

Fuente: API-Football (https://www.api-football.com). Necesita una clave propia y un plan que incluya la temporada
que pidas (el plan gratuito NO suele dar la temporada actual). La clave se pasa por variable de entorno, nunca se guarda.

  APIFOOTBALL_KEY=tu_clave python3 build_stats.py            # temporada 2025 (2025/26)
  APIFOOTBALL_KEY=tu_clave python3 build_stats.py 2026       # temporada 2026/27
  python3 build_stats.py --from-file respuestas.json         # prueba sin red: lista de respuestas de /players ya guardadas

Cada página de /players?league=140&season=AAAA&page=N trae 20 jugadores; son ~35 páginas por temporada.
Solo usa la librería estándar de Python.
"""
import json, os, re, sys, time, unicodedata, urllib.request, datetime

URL = "https://v3.football.api-sports.io/players?league=140&season={season}&page={page}"

# trozos del nombre que da la API -> nombre del equipo en data.js
TEAMS = {
 "alaves": "Alavés", "athletic": "Athletic", "atletico": "Atlético de Madrid", "barcelona": "FC Barcelona",
 "betis": "Betis", "celta": "Celta", "deportivo": "Deportivo", "elche": "Elche", "espanyol": "Espanyol",
 "getafe": "Getafe", "levante": "Levante", "malaga": "Málaga", "osasuna": "Osasuna", "racing": "Racing Santander",
 "rayo": "Rayo Vallecano", "real madrid": "Real Madrid", "real sociedad": "Real Sociedad", "sevilla": "Sevilla",
 "valencia": "Valencia", "villarreal": "Villarreal", "girona": "Girona", "mallorca": "Mallorca", "oviedo": "Oviedo",
}

def plain(s):
    s = unicodedata.normalize("NFD", s or "").lower()
    return re.sub(r"[^a-z0-9 ]+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn")).strip()

def team_name(api_name):
    p = plain(api_name)
    for k in sorted(TEAMS, key=len, reverse=True):        # "real madrid" antes que "madrid"
        if k in p:
            return TEAMS[k]
    return api_name

def n(x):
    return x if isinstance(x, (int, float)) else 0

def fetch(season, key):
    pages, page, total = [], 1, 1
    while page <= total:
        req = urllib.request.Request(URL.format(season=season, page=page), headers={"x-apisports-key": key})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            msg = {401: "clave no válida", 403: "clave rechazada: comprueba que es la real (no el texto 'tu_clave') y que tu plan está activo",
                   429: "demasiadas peticiones: espera un minuto y repite"}.get(e.code, "error HTTP")
            sys.exit("API-Football respondió %d: %s" % (e.code, msg))
        if d.get("errors"):
            sys.exit("La API devolvió un error: %s" % d["errors"])
        pages.append(d)
        total = d.get("paging", {}).get("total", 1)
        print("página %d/%d" % (page, total), file=sys.stderr)
        page += 1
        time.sleep(6.5)                                   # el plan gratuito permite ~10 peticiones por minuto
    return pages

def convert(pages):
    """Une las distintas filas de un mismo jugador (cedidos, varios equipos) y aplana las estadísticas."""
    out = {}
    for d in pages:
        for item in d.get("response", []):
            p = item["player"]
            first = (p.get("firstname") or "").split(" ")[0]
            last = (p.get("lastname") or "").split(" ")[0]
            display = (first + " " + last).strip() or p.get("name", "")
            for st in item.get("statistics", []):
                g, sh, pa, ta, du, dr, fo, ca, pe = (st.get(k) or {} for k in
                    ("games", "shots", "passes", "tackles", "duels", "dribbles", "fouls", "cards", "penalty"))
                gl = st.get("goals") or {}
                row = out.setdefault((plain(display), team_name((st.get("team") or {}).get("name", ""))), {
                    "n": display, "a": p.get("name", ""), "t": team_name((st.get("team") or {}).get("name", "")), "s": {}})
                s = row["s"]
                for k, v in {
                    "games": n(g.get("appearences")), "minutes": n(g.get("minutes")),
                    "goals": n(gl.get("total")), "assists": n(gl.get("assists")), "saves": n(gl.get("saves")),
                    "shots": n(sh.get("total")), "shots_on": n(sh.get("on")),
                    "key_passes": n(pa.get("key")),
                    "tackles": n(ta.get("total")), "interceptions": n(ta.get("interceptions")),
                    "duels": n(du.get("total")), "duels_won": n(du.get("won")),
                    "dribbles": n(dr.get("attempts")), "dribbles_ok": n(dr.get("success")), "dribbled_past": n(dr.get("past")),
                    "fouls_drawn": n(fo.get("drawn")), "fouls_committed": n(fo.get("committed")),
                    "yellow": n(ca.get("yellow")), "yellowred": n(ca.get("yellowred")), "red": n(ca.get("red")),
                    "pen_won": n(pe.get("won")), "pen_committed": n(pe.get("commited")),   # (sic) así lo escribe la API
                    "pen_scored": n(pe.get("scored")), "pen_missed": n(pe.get("missed")), "pen_saved": n(pe.get("saved")),
                }.items():
                    s[k] = s.get(k, 0) + v
    return sorted(out.values(), key=lambda r: (r["t"], r["n"]))

def main():
    args = sys.argv[1:]
    if args and args[0] == "--from-file":
        pages = json.load(open(args[1], encoding="utf-8"))
        season = "fixture"
    else:
        key = os.environ.get("APIFOOTBALL_KEY")
        if not key:
            sys.exit("Falta la variable de entorno APIFOOTBALL_KEY (la clave de API-Football).")
        season = args[0] if args else "2025"
        pages = fetch(season, key)
    players = convert(pages)
    data = {"season": "%s/%s" % (season, str(int(season) + 1)[2:]) if season.isdigit() else season,
            "built": datetime.datetime.now(datetime.timezone.utc).isoformat(), "source": "API-Football", "players": players}
    with open("estadisticas.js", "w", encoding="utf-8") as f:
        f.write("window.PSTATS = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print("estadisticas.js: %d jugadores" % len(players))

if __name__ == "__main__":
    main()
