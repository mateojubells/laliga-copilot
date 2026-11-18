#!/usr/bin/env python3
"""Descarga resultados de Primera División (openfootball) y genera data.js.
Uso: python3 build_data.py
"""
import re, json, urllib.request, datetime, sys

BASE = "https://raw.githubusercontent.com/openfootball/espana/master/{}/1-liga.txt"
SEASONS = ["2025-26", "2026-27"]
MONTHS = {m: i + 1 for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}

# nombre en el dataset -> (nombre corto, alias para reconocimiento de voz)
TEAMS = {
 "Deportivo Alavés": ("Alavés", ["alaves", "el alaves", "glorioso"]),
 "Athletic Club": ("Athletic", ["athletic", "athletic club", "athletic de bilbao", "bilbao", "leones"]),
 "Club Atlético de Madrid": ("Atlético de Madrid", ["atletico de madrid", "atletico", "atleti", "colchoneros", "club atletico de madrid"]),
 "FC Barcelona": ("FC Barcelona", ["barcelona", "barca", "barça", "fc barcelona", "culés", "cules", "blaugranas"]),
 "Real Betis Balompié": ("Betis", ["betis", "real betis", "verdiblancos"]),
 "RC Celta de Vigo": ("Celta", ["celta", "celta de vigo", "celestes"]),
 "RC Deportivo La Coruña": ("Deportivo", ["deportivo", "depor", "deportivo de la coruña", "la coruña", "coruña"]),
 "Elche CF": ("Elche", ["elche", "franjiverdes"]),
 "RCD Espanyol de Barcelona": ("Espanyol", ["espanyol", "espanyol de barcelona", "periquitos", "españyol"]),
 "Getafe CF": ("Getafe", ["getafe", "azulones"]),
 "Levante UD": ("Levante", ["levante", "granotas"]),
 "Málaga CF": ("Málaga", ["malaga", "boquerones"]),
 "CA Osasuna": ("Osasuna", ["osasuna", "rojillos"]),
 "Real Racing Club de Santander": ("Racing Santander", ["racing", "racing de santander", "santander", "racing santander"]),
 "Rayo Vallecano de Madrid": ("Rayo Vallecano", ["rayo", "rayo vallecano", "vallecas", "franjirrojos"]),
 "Real Madrid CF": ("Real Madrid", ["real madrid", "madrid", "merengues", "blancos", "vikingos"]),
 "Real Sociedad de Fútbol": ("Real Sociedad", ["real sociedad", "la real", "sociedad", "txuri urdin"]),
 "Sevilla FC": ("Sevilla", ["sevilla", "sevillistas", "nervionenses"]),
 "Valencia CF": ("Valencia", ["valencia", "che", "valencianistas"]),
 "Villarreal CF": ("Villarreal", ["villarreal", "submarino amarillo", "groguets"]),
}

# Nombres del dataset 2025-26 (distintos a los de 2026-27)
ALIAS_2526 = {
 "Athletic Club": "Athletic", "Atlético de Madrid": "Atlético de Madrid", "Barcelona": "FC Barcelona",
 "CA Osasuna": "Osasuna", "Deportivo Alavés": "Alavés", "Elche CF": "Elche", "Getafe CF": "Getafe",
 "Levante UD": "Levante", "RC Celta": "Celta", "RCD Espanyol": "Espanyol", "Rayo Vallecano": "Rayo Vallecano",
 "Real Betis": "Betis", "Real Madrid C.F.": "Real Madrid", "Real Sociedad": "Real Sociedad", "Sevilla": "Sevilla",
 "Valencia CF": "Valencia", "Villarreal": "Villarreal",
 # descendidos (siguen apareciendo en la temporada 25/26)
 "Girona FC": "Girona", "RCD Mallorca": "Mallorca", "Real Oviedo": "Oviedo",
}

def fetch(season):
    url = BASE.format(season)
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode("utf-8")

def parse(season, text):
    y0 = int(season[:4])
    out, cur = [], None
    date_re = re.compile(r"^\s{2}(\w{3}) (\w{3}) (\d+)(?: (\d{4}))?\s*$")
    match_re = re.compile(r"^\s+(?:(\d\d:\d\d)\s+)?(.+?)\s+v\s+(.+?)(?:\s+(\d+)-(\d+)(?:\s+\((\d+)-(\d+)\))?)?\s*$")
    for line in text.splitlines():
        m = date_re.match(line)
        if m:
            _, mon, day, yr = m.groups()
            mon = MONTHS[mon]
            year = int(yr) if yr else (y0 if mon >= 7 else y0 + 1)
            cur = datetime.date(year, mon, int(day))
            continue
        m = match_re.match(line)
        if m and cur and not line.lstrip().startswith(("#", "=", "▪")):
            t, h, a, fh, fa, hh, ha = m.groups()
            h, a = h.strip(), a.strip()
            if h not in TEAMS or a not in TEAMS:
                print("Equipo desconocido:", h, "|", a, file=sys.stderr); continue
            out.append({
                "season": season, "date": cur.isoformat(), "time": t or "",
                "home": TEAMS[h][0], "away": TEAMS[a][0],
                "ft": [int(fh), int(fa)] if fh is not None else None,
                "ht": [int(hh), int(ha)] if hh is not None else None,
            })
    return out

GOAL_RE = re.compile(r"^(.+?)\s+(\d+)(?:\+(\d+))?'\s*(?:\((p|og)\))?$")

def parse_goals(block, hs, as_):
    """block: texto entre parentesis. izquierda de ';' = local, derecha = visitante."""
    block = block.strip()
    if block.startswith("(") and block.endswith(")"):
        block = block[1:-1]
    if ";" in block:
        left, right = block.split(";", 1)
        sides = [("h", left), ("a", right)]
    else:
        sides = [("h" if hs > 0 and as_ == 0 else "a" if as_ > 0 and hs == 0 else "h", block)]
        # si ambos marcaron sin ';' no es fiable: se asigna al local
    goals = []
    for side, txt in sides:
        prev = None
        for part in txt.split(","):
            part = " ".join(part.split())
            if not part: continue
            if re.match(r"^\d", part) and prev:   # "Nombre 16', 28'": mismo jugador
                part = prev + " " + part
            m = GOAL_RE.match(part)
            if not m:
                print("  goleador sin parsear:", repr(part), file=sys.stderr); continue
            name, mi, extra, kind = m.groups()
            prev = name
            goals.append({"n": name, "m": int(mi), "x": mi + ("+" + extra if extra else ""),
                          "t": kind or "", "s": side})
    return goals

def parse_scorers(season, text):
    y0 = int(season[:4])
    date_re = re.compile(r"^(\w{3}) (\w{3}) (\d+)(?: (\d{4}))?\s*$")
    match_re = re.compile(r"^\s+(\d\d:\d\d)\s+(.+?)\s{2,}(\d+)-(\d+)(?:\s+\((\d+)-(\d+)\))?\s+(.+?)\s*$")
    out, cur, last, buf = [], None, None, []
    def flush():
        nonlocal buf, last
        if last is not None and buf:
            last["goals"] = parse_goals(" ".join(buf), last["ft"][0], last["ft"][1])
        buf = []
    for line in text.splitlines():
        m = date_re.match(line)
        if m:
            flush(); last = None
            _, mon, day, yr = m.groups(); mon = MONTHS[mon]
            cur = datetime.date(int(yr) if yr else (y0 if mon >= 7 else y0 + 1), mon, int(day)); continue
        m = match_re.match(line)
        if m and cur:
            flush()
            t, h, fh, fa, hh, ha, a = m.groups()
            if h not in ALIAS_2526 or a not in ALIAS_2526:
                print("Equipo desconocido 25/26:", h, "|", a, file=sys.stderr); last = None; continue
            last = {"season": season, "date": cur.isoformat(), "time": t,
                    "home": ALIAS_2526[h], "away": ALIAS_2526[a],
                    "ft": [int(fh), int(fa)], "ht": [int(hh), int(ha)] if hh is not None else None, "goals": []}
            out.append(last); continue
        if line.startswith("▪") or not line.strip():
            flush(); continue
        if last is not None and line.startswith("  "):
            buf.append(line.strip())
    flush()
    return out

matches = []
for s in SEASONS:
    ms = parse_scorers(s, fetch(s)) if s == "2025-26" else parse(s, fetch(s))
    print(s, len(ms), "partidos,", sum(1 for m in ms if m["ft"]), "jugados")
    matches += ms
matches.sort(key=lambda m: (m["date"], m["time"]))
teams = [{"name": v[0], "aliases": v[1]} for v in TEAMS.values()]
data = {"built": datetime.datetime.now(datetime.timezone.utc).isoformat(), "currentSeason": SEASONS[-1],
        "teams": teams, "matches": matches}
with open("data.js", "w", encoding="utf-8") as f:
    f.write("window.DATA = " + json.dumps(data, ensure_ascii=False) + ";\n")
print("data.js escrito")
