"""Temporadas intercambiables: una temporada FICTICIA (4 equipos) instalada en un directorio temporal."""
import hashlib
import json

import pytest

from copilot import seasons
from copilot.data.composite import CompositeProvider
from copilot.data.openfootball import OpenFootballProvider
from copilot.data.synthetic import SyntheticDataMissing
from copilot.nlu import engine as nlu_engine
from copilot.nlu import gazetteer
from data import import_season as imp

S = "2031-32"
TEAMS = {  # id: (name, short, nombre en los resultados, apellido-sufijo)
    "norte": ("Club Deportivo Norte", "Norte", "CD Norte", "tanilla"),
    "sur": ("Unión Sur", "Sur", "Sur FC", "ero"),
    "este": ("Este Atlético", "Este", "Este Atlético", "ez"),
    "oeste": ("Oeste CF", "Oeste", "Oeste CF", "oso"),
}
STEMS = ["Quin", "Vald", "Mor", "Tal", "Bren", "Cor", "Fer", "Gal", "Hern", "Isl", "Jar", "Lun", "Mar", "Nor", "Orl",
         "Pen", "Rav", "Sal", "Tor", "Ulm", "Vel", "Zam"]
POSITIONS = ["GK", "GK", "RB", "RB", "CB", "CB", "CB", "LB", "LB", "DM", "DM", "CM", "CM", "CM", "AM", "RW", "RW",
             "LW", "LW", "ST", "ST", "ST"]
LINE = imp.LINE_OF


def make_roster() -> dict:
    teams = []
    for tid, (name, short, _, suf) in TEAMS.items():
        players = []
        for k, pos in enumerate(POSITIONS):
            surname = STEMS[k] + suf
            players.append(dict(id=f"{tid}/{surname.lower()}", team=tid, name=f"Pablo {surname}", known_as=surname,
                                number=k + 1, position=pos, line=LINE[pos], foot="R", born=1998, nationality="ESP",
                                aliases=[surname.lower()], asr_aliases=[], epithets=[]))
        teams.append(dict(id=tid, name=name, short=short, aliases=[short.lower()], colors={"primary": "#112233"},
                          coach="Mister X", stadium="Estadio " + short, players=players))
    return {"season": S, "teams": teams}


def make_results() -> dict:
    ids = list(TEAMS)
    pairs = [(0, 1), (2, 3), (0, 2), (1, 3), (0, 3), (1, 2)]  # 3 jornadas de ida; la vuelta invierte
    rounds = [[(ids[a], ids[b]) for a, b in pairs[i * 2:i * 2 + 2]] for i in range(3)]
    rounds += [[(b, a) for a, b in r] for r in rounds]
    matches = []
    for n, r in enumerate(rounds, 1):
        for k, (h, a) in enumerate(r):
            matches.append({"round": f"Matchday {n}", "date": f"2031-09-{n:02d}", "team1": TEAMS[h][2],
                            "team2": TEAMS[a][2], "score": {"ht": [0, 0], "ft": [(n + k) % 3, (n * 2 + k) % 2]}})
    return {"name": "Ficticia 2031/32", "matches": matches}


@pytest.fixture()
def fake(tmp_path, monkeypatch):
    """Rutas de copilot.seasons apuntando a un directorio temporal con la temporada ficticia SIN instalar."""
    base = {name: tmp_path / name for name in ("rosters", "real", "synth", "matches", "sessions")}
    for d in base.values():
        d.mkdir()
    monkeypatch.setattr(seasons, "ROSTERS", base["rosters"])
    monkeypatch.setattr(seasons, "REAL", base["real"])
    monkeypatch.setattr(seasons, "SYNTH", base["synth"])
    monkeypatch.setattr(seasons, "MATCHES", base["matches"])
    src = tmp_path / "src"
    src.mkdir()
    (src / "rosters.json").write_text(json.dumps(make_roster(), ensure_ascii=False), encoding="utf-8")
    (src / "results.json").write_text(json.dumps(make_results(), ensure_ascii=False), encoding="utf-8")
    imp._clear_caches()
    yield src
    imp._clear_caches()


def install(src, **kw):
    kw.setdefault("stats", False)
    return imp.import_season(S, rosters=src / "rosters.json", results=src / "results.json", out=lambda s: None, **kw)


# ------------------------------------------------------------------ instalación
def test_importa_e_instala_la_temporada(fake):
    assert S not in seasons.installed()
    s = install(fake)
    assert S in seasons.installed() and seasons.installed()[0] == S  # la más reciente primero
    assert (s.teams, s.players, s.matches, s.played, s.stats) == (4, 4 * len(POSITIONS), 12, 12, False)
    assert seasons.roster_path(S).exists() and seasons.results_path(S).exists()
    assert S in seasons.results_seasons()
    info = seasons.info(S)
    assert (info.teams, info.has_results, info.has_stats) == (4, True, False)
    assert "4" in s.text() and S in s.text()


def test_reimportar_es_idempotente(fake):
    install(fake)
    h = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()  # noqa: E731
    before = (h(seasons.roster_path(S)), h(seasons.results_path(S)))
    install(fake)
    assert (h(seasons.roster_path(S)), h(seasons.results_path(S))) == before
    # sin --rosters ni --results valida lo ya instalado
    assert imp.main(["--season", S, "--no-stats"]) == 0
    assert (h(seasons.roster_path(S)), h(seasons.results_path(S))) == before


def test_fetch_con_descarga_simulada(fake):
    imp.import_season(S, rosters=fake / "rosters.json", stats=False, out=lambda s: None)  # solo plantillas
    assert seasons.results_seasons() == []
    urls = []

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return (fake / "results.json").read_bytes()

    def opener(url, timeout=None):
        urls.append(url)
        return Resp()

    s = imp.import_season(S, fetch=True, stats=False, out=lambda s: None, opener=opener)
    assert urls == [f"https://raw.githubusercontent.com/openfootball/football.json/master/{S}/es.1.json"]
    assert s.matches == 12 and S in seasons.results_seasons()


def test_fetch_fallido_da_error_claro(fake):
    def opener(url, timeout=None):
        raise OSError("404 Not Found")

    with pytest.raises(imp.ImportFailed, match="--fetch: no se pudo descargar .*404"):
        imp.import_season(S, rosters=fake / "rosters.json", fetch=True, stats=False, out=lambda s: None, opener=opener)
    assert S not in seasons.installed()  # no se instala nada a medias


# ------------------------------------------------------------------ capas que consumen la temporada
def test_gazetteer_carga_la_temporada(fake):
    install(fake)
    d = gazetteer.season(S)
    assert [t["id"] for t in d["teams"]] == list(TEAMS)
    assert gazetteer.season()["teams"] == d["teams"]  # None = seasons.current() = la única instalada
    g = gazetteer.Gazetteer(("norte", "sur"), f"{S}/J01/norte-sur")
    assert g.season == S and "norte/quintanilla" in g.players and "barcelona" not in g.teams
    assert [c.id for c in g.exact["quintanilla"]] == ["norte/quintanilla"]


def test_motor_reconoce_a_los_jugadores_de_la_temporada(fake):
    install(fake)
    eng = nlu_engine.Engine()
    eng.reset(match_id=f"{S}/J01/norte-sur")
    assert eng.match_teams == ("norte", "sur")
    res = eng.analyze("gol de Quintanilla, la pone Valdero")
    assert {e.id for e in res.entities} >= {"norte/quintanilla", "sur/valdero"}
    assert [(e.type, e.roles.get("actor")) for e in res.events][:1] == [("gol", "norte/quintanilla")]
    # el motor de otra temporada sigue funcionando en el mismo proceso
    nlu_engine.clear_caches()
    assert not nlu_engine._GAZ


def test_motor_cambia_de_temporada_con_el_partido(fake):
    install(fake)
    eng = nlu_engine.Engine()
    eng.reset(match_id=f"{S}/J01/norte-sur")
    assert eng.gaz.season == S
    eng.reset()  # sin partido: temporada activa
    assert eng.gaz.season == seasons.current()


def test_openfootball_da_la_clasificacion(fake):
    install(fake)
    p = OpenFootballProvider()
    assert {t.id for t in p.teams(S)} == set(TEAMS) and p.teams(S)[0].name == TEAMS["norte"][0]
    ms = p.matches(S)
    assert len(ms) == 12 and ms[0].id == f"{S}/J01/este-oeste" and {m.home for m in ms} == set(TEAMS)
    table = p.standings(S)
    assert len(table) == 4 and sum(r.played for r in table) == 24
    assert sum(r.gf for r in table) == sum(r.ga for r in table) == sum(m.home_goals + m.away_goals for m in ms)
    assert [r.pos for r in table] == [1, 2, 3, 4]
    assert len(p.standings(S, until_round=2)[0].form) <= 2
    assert p.h2h("norte", "sur").played == 2  # ida y vuelta (solo hay esta temporada con resultados)


def test_equipo_ascendido_se_reconoce_por_alias(fake):
    r = make_results()
    r["matches"][0]["team1"] = "C.D. Norte"  # no coincide con name/short: solo con el alias de la plantilla
    (fake / "results.json").write_text(json.dumps(r), encoding="utf-8")
    ro = make_roster()
    ro["teams"][0]["aliases"].append("c.d. norte")
    (fake / "rosters.json").write_text(json.dumps(ro), encoding="utf-8")
    install(fake)
    assert f"{S}/J01/norte-sur" in {m.id for m in OpenFootballProvider().matches(S)}


def test_compuesto_resuelve_la_temporada_por_llamada(fake):
    install(fake)
    c = CompositeProvider()  # sin temporada: la activa
    assert c.season is None and c.synth.season == S and c.available() is False
    assert [t.id for t in c.teams(S)] == list(TEAMS)
    assert len(c.squad("norte", S)) == len(POSITIONS)
    with pytest.raises(SyntheticDataMissing):
        c.player_season("norte/quintanilla", S)
    with pytest.raises(SyntheticDataMissing):
        c.events(f"{S}/J01/norte-sur")
    assert CompositeProvider(season=S).available(S) is False


def test_generacion_de_estadisticas_de_la_temporada(fake):
    from data.synth.generate import generate
    install(fake)
    out = generate(season=S, rounds="1-2", verbose=False)
    assert out == seasons.synth_db(S) and out.exists()
    c = CompositeProvider()
    assert c.available(S) is True
    ps = c.player_season("norte/quintanilla", S)
    assert ps.season == S and ps.minutes >= 0
    ev = c.events(f"{S}/J01/norte-sur")
    assert ev and {e.match for e in ev} == {f"{S}/J01/norte-sur"}
    assert c.synth_for(S).meta()["season"] == S and not c.synth_for(S).stale
    assert c.pass_network("norte", match_id=f"{S}/J01/norte-sur").nodes
    assert seasons.info(S).has_stats


# ------------------------------------------------------------------ ficheros inválidos
def fail(src, roster=None, results=None, match=None, **kw):
    if roster is not None:
        (src / "rosters.json").write_text(json.dumps(roster), encoding="utf-8")
    if results is not None:
        (src / "results.json").write_text(json.dumps(results), encoding="utf-8")
    with pytest.raises(imp.ImportFailed) as e:
        install(src, **kw)
    assert S not in seasons.installed() and not seasons.results_path(S).exists()  # no se instaló nada
    text = "\n".join(e.value.errors)
    if match:
        assert match in text, text
    return text


def mod(fn):
    r = make_roster()
    fn(r)
    return r


def test_json_roto(fake):
    (fake / "rosters.json").write_text("{no es json", encoding="utf-8")
    assert "JSON inválido en la línea 1" in fail(fake)


def test_plantillas_error_de_formato_con_ruta(fake):
    t = fail(fake, mod(lambda r: r["teams"][1]["players"][3].update(id="sur/Con Acento")),
             match="teams[1] (id=sur).players[3]")
    assert "formato 'equipo/slug'" in t
    fail(fake, mod(lambda r: r["teams"][0]["players"][2].update(id="sur/otro")), match="el prefijo debe ser")
    fail(fake, mod(lambda r: r["teams"][0]["players"][5].update(id=r["teams"][0]["players"][4]["id"])),
         match="id: duplicado")
    fail(fake, mod(lambda r: r["teams"][2].update(id="norte")), match="teams[2] (id=norte).id: duplicado")
    fail(fake, mod(lambda r: r["teams"][0].update(id="Norte Raro")), match="slug en minúsculas")


def test_plantillas_linea_posicion_porteros_y_tamano(fake):
    fail(fake, mod(lambda r: r["teams"][0]["players"][4].update(line="FWD")), match="no es coherente con position 'CB'")
    fail(fake, mod(lambda r: r["teams"][0]["players"][4].update(position="XX")), match="players[4]")

    def un_portero(r):
        r["teams"][3]["players"][1].update(position="CB", line="DEF")
    fail(fake, mod(un_portero), match="1 porteros")

    def pocos(r):
        r["teams"][1]["players"] = r["teams"][1]["players"][:9]
    t = fail(fake, mod(pocos), match="9 jugadores, mínimo 11")
    assert "teams[1]" in t
    fail(fake, mod(lambda r: r["teams"][0]["players"][3].update(number=1)), match="dorsal 1")
    fail(fake, mod(lambda r: r["teams"][0]["players"][3].update(team="sur")), match=".team: es 'sur'")
    fail(fake, {"season": S, "teams": []}, match="lista `teams` no vacía")
    fail(fake, mod(lambda r: r.update(season="2030-31")), match="rosters.season")


def test_resultados_con_equipos_sin_plantilla(fake):
    r = make_results()
    r["matches"][0]["team1"] = "Atlético Fantasma"
    r["matches"][5]["team2"] = "Real Imaginario"
    r["matches"][6]["team2"] = "Real Imaginario"
    t = fail(fake, roster=make_roster(), results=r)
    assert "'Atlético Fantasma'" in t and "'Real Imaginario'" in t and "+1 más" in t


def test_resultados_formato(fake):
    r = make_results()
    r["matches"][2]["round"] = "Jornada 3"
    r["matches"][3]["score"] = {"ft": [1]}
    r["matches"][4]["date"] = "3/9/2031"
    t = fail(fake, roster=make_roster(), results=r)
    assert "matches[2].round" in t and "matches[3].score.ft" in t and "matches[4].date" in t
    fail(fake, results={"matches": []}, match="lista `matches` no vacía")
    r = make_results()
    r["matches"].append(dict(r["matches"][0]))
    fail(fake, results=r, match="partido repetido")


def test_temporada_mal_formada_y_sin_plantillas(fake):
    with pytest.raises(imp.ImportFailed, match="formato AAAA-AA"):
        imp.import_season("2031", stats=False)
    with pytest.raises(imp.ImportFailed, match="no son consecutivos"):
        imp.import_season("2031-35", stats=False)
    with pytest.raises(imp.ImportFailed, match="No hay plantillas de 2031-32.*--rosters"):
        imp.import_season(S, stats=False)
    with pytest.raises(imp.ImportFailed, match="excluyentes"):
        imp.import_season(S, results="x.json", fetch=True)


def test_cli_devuelve_error_y_no_instala(fake, capsys):
    ro = make_roster()
    ro["teams"][0]["players"][0]["line"] = "FWD"
    (fake / "rosters.json").write_text(json.dumps(ro), encoding="utf-8")
    assert imp.main(["--season", S, "--rosters", str(fake / "rosters.json"), "--no-stats"]) == 1
    err = capsys.readouterr().err
    assert "No se instaló nada" in err and "teams[0] (id=norte).players[0]" in err
    assert imp.main(["--season", S, "--rosters", str(fake / "rosters.json"), "--results", "/no/existe.json"]) == 1
    assert S not in seasons.installed()


# ------------------------------------------------------------------ la temporada real sigue igual
def test_importar_2024_25_sin_estadisticas_es_idempotente():
    files = [seasons.roster_path("2024-25"), seasons.results_path("2024-25")]
    before = [f.read_bytes() for f in files]
    assert imp.main(["--season", "2024-25", "--no-stats"]) == 0
    assert [f.read_bytes() for f in files] == before
    assert "2024-25" in seasons.installed()
    assert seasons.info("2024-25").teams == 20
