"""Descarga el wikitext de las páginas de temporada 2024-25 (se guarda en raw/<equipo>.wikitext)."""
import json, subprocess, sys, time, urllib.parse
from pathlib import Path
RAW = Path(__file__).parent / "raw"
D = "–"
PAGES = {
 "alaves": "Deportivo Alavés", "athletic": "Athletic Bilbao", "atletico": "Atlético Madrid",
 "barcelona": "FC Barcelona", "betis": "Real Betis", "celta": "RC Celta de Vigo",
 "espanyol": "RCD Espanyol", "getafe": "Getafe CF", "girona": "Girona FC", "las-palmas": "UD Las Palmas",
 "leganes": "CD Leganés", "mallorca": "RCD Mallorca", "osasuna": "CA Osasuna", "rayo": "Rayo Vallecano",
 "real-madrid": "Real Madrid CF", "real-sociedad": "Real Sociedad", "sevilla": "Sevilla FC",
 "valencia": "Valencia CF", "valladolid": "Real Valladolid", "villarreal": "Villarreal CF"}
def fetch(title):
    url = ("https://en.wikipedia.org/w/api.php?action=parse&page=" + urllib.parse.quote(title)
           + "&prop=wikitext&format=json&redirects=1")
    out = subprocess.run(["curl", "-s", "-m", "40", "-A", "roster-builder/1.0", url], capture_output=True).stdout
    try: return json.loads(out)["parse"]["wikitext"]["*"]
    except Exception: return None
if __name__ == "__main__":
    only = sys.argv[1:] or list(PAGES)
    for tid in only:
        f = RAW / f"{tid}.wikitext"
        if f.exists(): continue
        t = fetch(f"2024{D}25 {PAGES[tid]} season")
        print(tid, "OK" if t else "FALTA", len(t or ""))
        if t: f.write_text(t, encoding="utf-8")
        time.sleep(1)

# Clubes cuya página de temporada no trae plantilla: revisión de la página del club a 1 oct 2024
CLUB_PAGES = {"valladolid": "Real Valladolid", "getafe": "Getafe CF", "leganes": "CD Leganés", "rayo": "Rayo Vallecano"}
def fetch_club_revision(title, ts="2024-10-01T00:00:00Z"):
    url = ("https://en.wikipedia.org/w/api.php?action=query&prop=revisions&rvprop=content|ids&rvslots=main"
           "&rvlimit=1&rvdir=older&rvstart=" + ts + "&format=json&titles=" + urllib.parse.quote(title))
    out = subprocess.run(["curl", "-s", "-m", "40", "-A", "roster-builder/1.0", url], capture_output=True).stdout
    try:
        page = next(iter(json.loads(out)["query"]["pages"].values()))
        rev = page["revisions"][0]
        return rev["revid"], rev["slots"]["main"]["*"]
    except Exception:
        return None, None
