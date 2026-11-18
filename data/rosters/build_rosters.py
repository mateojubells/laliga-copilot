#!/usr/bin/env python3
"""Construye data/rosters/2024-25.json a partir de los wikitext descargados en raw/.

Uso:  .venv/bin/python data/rosters/build_rosters.py [equipo ...]
      (sin argumentos: todos los equipos cuyo raw exista)

Fuentes (todas de Wikipedia en inglés, ver fetch_raw.py):
  raw/<equipo>.wikitext       página "2024-25 <club> season" (plantilla {{Fs player}} / {{fb si player}} / tabla)
  raw/<equipo>.club.wikitext  revisión de la página del club a 1-oct-2024 (Valladolid, Getafe, Leganés, Rayo,
                              cuyas páginas de temporada no traen plantilla)
  raw/born.json               año de nacimiento vía Wikidata (caché; se rellena con --born)
De Wikipedia salen: nombre, dorsal, línea (GK/DF/MF/FW), nacionalidad, año de nacimiento, entrenador, estadio.
Del conocimiento futbolístico (tablas de este fichero): posición fina, pie, apodos/known_as, colores, alias.
Los ids de jugadores del Barça-Valladolid se toman de eval/gold/barca-valladolid.truth.json (mismo dorsal + equipo).
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
RAW = HERE / "raw"
OUT = HERE / "2024-25.json"
LEGACY = ROOT / "legacy" / "plantillas.js"
TRUTH = ROOT / "eval" / "gold" / "barca-valladolid.truth.json"
WP = "https://en.wikipedia.org/wiki/"
D = "–"

# ----------------------------------------------------------------------------------------------------
# Equipos: metadatos a mano (alias de narración y colores no salen de Wikipedia)
# ----------------------------------------------------------------------------------------------------
TEAMS = {
    "alaves": dict(name="Deportivo Alavés", short="Alavés", page="Deportivo Alavés",
                   aliases=["alaves", "el alaves", "babazorros", "albiazules", "glorioso"],
                   colors=("#0761AF", "#FFFFFF", "#FFFFFF")),
    "athletic": dict(name="Athletic Club", short="Athletic", page="Athletic Bilbao",
                     aliases=["athletic", "athletic club", "athletic de bilbao", "bilbao", "leones", "rojiblancos"],
                     colors=("#EE2523", "#FFFFFF", "#FFFFFF")),
    "atletico": dict(name="Atlético de Madrid", short="Atlético", page="Atlético Madrid",
                     aliases=["atletico", "atletico de madrid", "atleti", "colchoneros", "rojiblancos", "indios"],
                     colors=("#CB3524", "#272E61", "#FFFFFF")),
    "barcelona": dict(name="FC Barcelona", short="Barça", page="FC Barcelona",
                      aliases=["barca", "barcelona", "fc barcelona", "azulgranas", "cules", "blaugrana", "blaugranas"],
                      colors=("#A50044", "#004D98", "#FFFFFF")),
    "betis": dict(name="Real Betis", short="Betis", page="Real Betis",
                  aliases=["betis", "real betis", "beticos", "verdiblancos", "heliopolitanos"],
                  colors=("#0BB363", "#FFFFFF", "#FFFFFF")),
    "celta": dict(name="RC Celta de Vigo", short="Celta", page="RC Celta de Vigo",
                  aliases=["celta", "celta de vigo", "celestes", "celtistas", "vigueses"],
                  colors=("#8AC3EE", "#E5254F", "#0B2A4A")),
    "espanyol": dict(name="RCD Espanyol", short="Espanyol", page="RCD Espanyol",
                     aliases=["espanyol", "espanol", "periquitos", "blanquiazules", "pericos"],
                     colors=("#007FC8", "#FFFFFF", "#FFFFFF")),
    "getafe": dict(name="Getafe CF", short="Getafe", page="Getafe CF",
                   aliases=["getafe", "azulones", "geta"],
                   colors=("#005999", "#FFFFFF", "#FFFFFF")),
    "girona": dict(name="Girona FC", short="Girona", page="Girona FC",
                   aliases=["girona", "gironins", "rojiblancos"],
                   colors=("#E1261C", "#FFFFFF", "#FFFFFF")),
    "las-palmas": dict(name="UD Las Palmas", short="Las Palmas", page="UD Las Palmas",
                       aliases=["las palmas", "la ud", "amarillos", "canarios", "pioneros"],
                       colors=("#FFE600", "#0E4DA4", "#0B2A4A")),
    "leganes": dict(name="CD Leganés", short="Leganés", page="CD Leganés",
                    aliases=["leganes", "pepineros", "lega", "cd leganes"],
                    colors=("#1D5DAE", "#FFFFFF", "#FFFFFF")),
    "mallorca": dict(name="RCD Mallorca", short="Mallorca", page="RCD Mallorca",
                     aliases=["mallorca", "bermellones", "mallorquinistas", "el mallorca"],
                     colors=("#E20613", "#000000", "#FFFFFF")),
    "osasuna": dict(name="CA Osasuna", short="Osasuna", page="CA Osasuna",
                    aliases=["osasuna", "rojillos", "el sadar"],
                    colors=("#D91A21", "#0A1D3F", "#FFFFFF")),
    "rayo": dict(name="Rayo Vallecano", short="Rayo", page="Rayo Vallecano",
                 aliases=["rayo", "rayo vallecano", "franjirrojos", "vallecanos", "rayistas"],
                 colors=("#FFFFFF", "#E53027", "#000000")),
    "real-madrid": dict(name="Real Madrid", short="Real Madrid", page="Real Madrid CF",
                        aliases=["real madrid", "madrid", "el madrid", "merengues", "blancos", "vikingos", "los blancos"],
                        colors=("#FFFFFF", "#FEBE10", "#00529F")),
    "real-sociedad": dict(name="Real Sociedad", short="Real Sociedad", page="Real Sociedad",
                          aliases=["real sociedad", "la real", "realistas", "txuri urdin", "donostiarras"],
                          colors=("#0067B1", "#FFFFFF", "#FFFFFF")),
    "sevilla": dict(name="Sevilla FC", short="Sevilla", page="Sevilla FC",
                    aliases=["sevilla", "sevillistas", "nervionenses", "palanganas"],
                    colors=("#FFFFFF", "#D4021D", "#D4021D")),
    "valencia": dict(name="Valencia CF", short="Valencia", page="Valencia CF",
                     aliases=["valencia", "che", "ches", "valencianistas", "murcielagos"],
                     colors=("#FFFFFF", "#000000", "#000000")),
    "valladolid": dict(name="Real Valladolid", short="Valladolid", page="Real Valladolid",
                       aliases=["valladolid", "real valladolid", "pucela", "pucelanos", "blanquivioletas", "el pucela"],
                       colors=("#5A1B6D", "#FFFFFF", "#FFFFFF")),
    "villarreal": dict(name="Villarreal CF", short="Villarreal", page="Villarreal CF",
                       aliases=["villarreal", "submarino amarillo", "groguets", "amarillos"],
                       colors=("#FBE122", "#005187", "#005187")),
}
CLUB_PAGE = {"valladolid": "Real Valladolid", "getafe": "Getafe CF", "leganes": "CD Leganés", "rayo": "Rayo Vallecano"}

# ----------------------------------------------------------------------------------------------------
# Listas de apoyo
# ----------------------------------------------------------------------------------------------------
PARTICLES = {"de", "del", "da", "dos", "das", "do", "di", "van", "von", "ter", "el", "al", "la", "le", "ben", "bin",
             "mac", "san", "santa", "den", "der", "dal", "lo"}
# Apellidos españoles muy frecuentes: nunca sueltos como alias; el known_as lleva nombre + apellido.
COMMON_SURNAMES = set("""garcia martin martinez lopez sanchez perez fernandez gonzalez rodriguez gomez ruiz diaz moreno
munoz alvarez romero alonso gutierrez navarro torres dominguez vazquez ramos gil serrano blanco molina morales suarez
ortega delgado castro ortiz rubio marin sanz iglesias nunez medina garrido cortes castillo santos lozano guerrero cano
prieto mendez cruz calvo gallego vidal leon marquez herrera pena flores cabrera campos vega fuentes carrasco diez
caballero reyes nieto aguilar pascual santana herrero montero lorenzo hidalgo gimenez ibanez ferrer duran santiago
benitez mora vicente vargas arias carmona crespo roman pastor soto saez velasco moya soler parra esteban bravo gallardo
rojas rey jimenez hernandez ruiz silva costa pereira ferreira santos oliveira souza almeida carvalho gomes ribeiro
rodrigues lima moura sousa fernandes mendes lopes alves pinto da silva da costa campo luna sol mar rios rio valle
montes bosque castillo palacios palacio perea sierra pozo pozos nuñez ponce salas vila villa gonzalo rosa rosas
lucas pablo pedro mateo marcos andres jorge pol rafa alex javi dani hugo mario david sergio luis juan jose carlos
manuel miguel antonio francisco victor ivan oscar adrian raul ruben diego nacho nico jon ander iker unai aitor""".split())
# Nombres de pila corrientes: no se usan solos como alias.
COMMON_FIRST = set("""david daniel dani juan jose javi javier carlos pablo pedro alex alejandro miguel manuel manu jorge
sergio luis antonio marc pau pol joan jordi oscar adrian ivan raul ruben victor mario diego nacho nico nicolas jon ander
iker gonzalo hugo oier unai aitor mikel inaki inigo alvaro aleix aleixo alberto andres angel carles carlo cesar christian
cristian eduardo edu enrique ernesto fernando francisco gabriel gerard guillermo ignacio isaac joel jonathan jorge
josep julian lucas marcos martin mateo mohamed mohammed nuno oliver omar pere peter ramon rafael robert roberto
ruben samuel santi santiago sebastian stefan thomas toni tomas xavi youssef yeray yan jan marco andre bruno pepe rafa
tony sami samu said sidi abdel ibrahima ousmane moussa abdoulaye mamadou amadou issa kevin lucas luka luca leo dario
erik eric fran gonzalo guille guido jaime jesus joaquin jonny josema kike koke kiko lazaro mauro max nelson nahuel
oriol paco pere pau quique roque salva sandro saul toño toni vicente victor yuri sergi hector gorka benat adria abel bryan enzo enric federico german alfonso valentin benito cristhian daley ronald andreas karl cenk ansu""".split())
# Palabras corrientes del castellano (sueltas nunca son alias). El test mantiene su propia lista independiente.
COMMON_WORDS = set("""torre fort campo bueno bravo rey cruz pastor sol mar luna rio cano gil mora vega roman soto parra pozo valle
duro claro blanco negro rojo verde alto bajo largo corto grande pequeno nuevo viejo joven mayor menor primero segundo
tercero ultimo medio centro lateral punta extremo portero delantero defensa pase tiro gol falta penalti corner saque
banda area balon pelota partido equipo jugador campeon liga copa final minuto tiempo parte gran buen mejor peor nada
todo algo nadie cosa vida casa dia noche ano mes semana hora vez forma modo lado fondo base cara mano pie cabeza
corazon fuerza luz sombra cielo tierra fuego agua viento paz guerra amor miedo suerte gracia ganas razon nombre
tomas ante pedro pablo juan jose luis carlos david daniel miguel angel antonio manuel marco victor mateo hugo leo""".split())

# known_as (nombre de narración) cuando no coincide con la heurística. Clave: nombre tal como sale en Wikipedia.
KNOWN_AS = {
    "Marc-André ter Stegen": "Ter Stegen", "Frenkie de Jong": "De Jong", "Vinícius Júnior": "Vinicius",
    "Dani Carvajal": "Carvajal", "Éder Militão": "Militão", "Aurélien Tchouaméni": "Tchouaméni",
    "Federico Valverde": "Valverde", "Trent Alexander-Arnold": "Alexander-Arnold", "Antonio Rüdiger": "Rüdiger",
    "Jude Bellingham": "Bellingham", "Kylian Mbappé": "Mbappé", "Thibaut Courtois": "Courtois",
    "Luka Modrić": "Modrić", "Eduardo Camavinga": "Camavinga", "Antoine Griezmann": "Griezmann",
    "Jan Oblak": "Oblak", "Koke": "Koke", "Rodrigo De Paul": "De Paul", "Álvaro Morata": "Morata",
    "Wojciech Szczęsny": "Szczęsny", "Robert Lewandowski": "Lewandowski", "Pau Cubarsí": "Cubarsí",
    "Alejandro Balde": "Balde", "Jules Koundé": "Koundé", "Ronald Araújo": "Araújo", "Marc Casadó": "Casadó",
    "Dani Olmo": "Dani Olmo", "Íñigo Martínez": "Íñigo Martínez", "Fermín López": "Fermín López",
    "Iñaki Peña": "Iñaki Peña", "Pablo Torre": "Pablo Torre", "Eric García": "Eric García",
    "Ferran Torres": "Ferran Torres", "Lamine Yamal": "Lamine Yamal", "Pau Víctor": "Pau Víctor",
    "Unai Simón": "Unai Simón", "Iñigo Ruiz de Galarreta": "Ruiz de Galarreta", "Luiz Júnior": "Luiz Júnior",
    "Iñaki Williams": "Iñaki Williams", "Nico Williams": "Nico Williams", "Fermín López": "Fermín López",
    "José Ángel Carmona": "Carmona", "José Ángel López": "José Ángel López", "Álvaro García Pascual": "García Pascual",
    "Jon Ander Olasagasti": "Olasagasti", "Urko González de Zárate": "González de Zárate", "Eric García": "Eric García",
    "Abdulai Juma Bah": "Bah", "Etienne Eto'o": "Eto'o", "Sandro Ramírez": "Sandro Ramírez",
    "Benito Ramírez": "Benito Ramírez", "Daley Blind": "Blind", "Daley Sinkgraven": "Sinkgraven",
    "Pau Cabanes": "Cabanes", "Marc Roca": "Marc Roca", "Juan Foyth": "Foyth", "Sergi Darder": "Darder",
    "Dani Parejo": "Parejo", "Dani Ceballos": "Ceballos", "Iago Aspas": "Aspas", "Isco": "Isco",
    "Dani Vivian": "Vivian", "Álvaro Valles": "Valles", "Pepe Reina": "Reina", "Giovani Lo Celso": "Lo Celso",
}

# Posición fina y pie ("POS" o "POS/L" o "/L") para quien NO es CB/CM/ST/GK por defecto. Conocimiento futbolístico
# 2024-25; el resto queda con el valor por defecto de la línea (DF->CB, MF->CM, FW->ST) y pie derecho.
POS_TABLE = """
alaves: guevara=DM antonio-blanco=DM carlos-vicente=RW manu-sanchez=LB/L tenaglia=RB conechny=RW villalibre=ST
athletic: gorosabel=RB unai-simon=GK vesga=DM berenguer=RW sancet=AM inaki-williams=RW nico-williams=LW/L lekue=RB
  berchiche=LB/L de-marcos=RB ruiz-de-galarreta=DM prados=DM boiro=LB djalo=LW
atletico: llorente=RB nahuel-molina=RB azpilicueta=RB lenglet=CB/L galan=LB/L koke=CM griezmann=AM correa=AM lemar=LW/L
  lino=LW/L julian-alvarez=ST simeone=RW riquelme=LW barrios=CM witsel=CB musso=GK oblak=GK
barcelona: kounde=RB balde=LB/L inigo-martinez=CB/L lamine-yamal=RW/L raphinha=LW fati=LW dani-olmo=AM pablo-torre=AM
  casado=DM bernal=DM hector-fort=RB gerard-martin=LB/L de-jong=CM eric-garcia=CB
betis: bellerin=RB perraud=LB/L ricardo-rodriguez=LB/L sabaly=RB ruibal=RB cardoso=DM william-carvalho=DM altimira=DM marc-roca=DM
  fornals=AM lo-celso=AM/L isco=AM antony=RW/L ezzalzouli=LW cucho-hernandez=ST avila=ST bakambu=ST
celta: mingueza=RB carreira=RB manquillo=RB kevin-vazquez=RB ristic=LB/L beltran=DM de-la-torre=DM cervi=RW alfon=LW
  bamba=LW swedberg=AM allende=AM aspas=ST douvikas=ST pablo-duran=ST hugo-alvarez=ST
espanyol: carlos-romero=LB/L olivan=LB/L carreras=RW puado=ST exposito=AM kral=DM pol-lozano=CM gonzalez-de-zarate=AM cheddira=ST
getafe: angileri=LB/L rico=LB/L juan-iglesias=RB arambarri=CM milla=DM mayoral=ST carles-perez=RW djene=CB soria=GK
girona: miguel-gutierrez=LB/L arnau-martinez=RB blind=CB/L van-de-beek=CM romeu=DM yangel-herrera=DM arthur=CM
  tsyhankov=RW danjuma=LW bryan-gil=LW/L asprilla=RW portu=RW stuani=ST abel-ruiz=ST miovski=ST
las-palmas: moleiro=AM/L sinkgraven=LB/L loiodice=DM campana=DM marmol=CB januzaj=RW pejino=RW mcburnie=ST cardona=ST
leganes: rosier=RB tapia=DM brasanac=DM neyou=DM oscar-rodriguez=AM raba=AM haller=ST de-la-fuente=ST nastasic=CB
mallorca: morey=RB lato=LB/L maffeo=RB mojica=LB/L mascarell=DM samu-costa=DM darder=AM dani-rodriguez=AM asano=RW muriqi=ST larin=ST
osasuna: nacho-vidal=RB areso=RB ruben-pena=RB bretones=LB/L torro=DM pablo-ibanez=DM moncayola=CM oroz=AM moi-gomez=RW
  zaragoza=LW/L barja=RW ruben-garcia=RW budimir=ST
rayo: ratiu=RB balliu=RB chavarria=LB/L espino=LB ciss=DM valentin=DM trejo=AM palazon=RW james-rodriguez=AM/L de-frutos=RW
  embarba=LW alvaro-garcia=LW/L de-tomas=ST nteka=ST guardiola=ST
real-madrid: carvajal=RB militao=CB alaba=CB/L lucas-vazquez=RB fran-garcia=LB/L mendy=LB/L rudiger=CB tchouameni=DM camavinga=CM
  bellingham=CM valverde=CM modric=CM guler=AM/L brahim-diaz=AM vinicius=LW rodrygo=RW mbappe=ST endrick=ST courtois=GK lunin=GK
real-sociedad: odriozola=RB aihen-munoz=LB/L traore=RB zubimendi=DM sucic=CM olasagasti=CM brais-mendez=AM/L kubo=RW/L
  barrenetxea=RW becker=RW oyarzabal=ST/L oskarsson=ST sergio-gomez=LW/L zakharyan=AM
sevilla: carmona=RB juanlu=RB pedrosa=LB/L gudelj=DM lokonga=DM agoume=DM saul=CM sow=CM suso=RW/L ruben-vargas=RW
  lukebakio=RW ejuke=LW isaac-romero=ST adams=ST
valencia: foulquier=RB correia=RB gaya=LB/L barrenechea=DM guillamon=DM pepelu=CM javi-guerra=CM andre-almeida=AM canos=RW
  rioja=LW fran-perez=RW valera=RW hugo-duro=ST dani-gomez=ST mir=ST
valladolid: kenedy=LW machis=LW sylla=ST meseguer=DM de-la-hoz=DM
villarreal: femenia=RB pedraza=LB/L foyth=CB comesana=DM gueye=DM parejo=CM denis-suarez=CM baena=AM buchanan=RW akhomach=RW
  pino=RW pepe=RW gerard-moreno=ST ayoze-perez=ST barry=ST
"""
POSITIONS: dict[str, tuple[str, str]] = {}
for _ln in POS_TABLE.strip().splitlines():
    if not _ln.startswith(" "):
        _team, _rest = _ln.split(":", 1)
    else:
        _rest = _ln
    for _tok in _rest.split():
        _slug, _val = _tok.split("=")
        _pos, _, _foot = _val.partition("/")
        POSITIONS[f"{_team}/{_slug}"] = (_pos or "", _foot or "R")

POS_BY_LINE = {"GK": "GK", "DF": "CB", "MF": "CM", "FW": "ST"}
LINE_OF = {"GK": "GK", "RB": "DEF", "CB": "DEF", "LB": "DEF", "DM": "MID", "CM": "MID", "AM": "MID",
           "RW": "FWD", "LW": "FWD", "ST": "FWD"}
LINE_CODE = {"GK": "GK", "DF": "DEF", "MF": "MID", "FW": "FWD"}
DEMONYM = {  # gentilicios; ESP se omite (en LaLiga no distingue)
    "ARG": "el argentino", "BRA": "el brasileño", "FRA": "el francés", "POR": "el portugués", "URU": "el uruguayo",
    "COL": "el colombiano", "GER": "el alemán", "ENG": "el inglés", "NED": "el neerlandés", "BEL": "el belga",
    "POL": "el polaco", "CRO": "el croata", "MAR": "el marroquí", "SEN": "el senegalés", "ITA": "el italiano",
    "SRB": "el serbio", "MEX": "el mexicano", "CHI": "el chileno", "VEN": "el venezolano", "PAR": "el paraguayo",
    "ECU": "el ecuatoriano", "PER": "el peruano", "NGA": "el nigeriano", "GHA": "el ghanés", "CMR": "el camerunés",
    "CIV": "el marfileño", "ALG": "el argelino", "EGY": "el egipcio", "JPN": "el japonés", "KOR": "el coreano",
    "USA": "el estadounidense", "GEO": "el georgiano", "UKR": "el ucraniano", "TUR": "el turco", "SUI": "el suizo",
    "AUT": "el austriaco", "DEN": "el danés", "SWE": "el sueco", "NOR": "el noruego", "SCO": "el escocés",
    "IRL": "el irlandés", "MKD": "el macedonio", "MNE": "el montenegrino", "BIH": "el bosnio", "ALB": "el albanés",
    "ROU": "el rumano", "HUN": "el húngaro", "CZE": "el checo", "SVK": "el eslovaco", "SVN": "el esloveno",
    "GRE": "el griego", "ISR": "el israelí", "EST": "el estonio", "GNB": "el guineano", "GUI": "el guineano",
    "GAM": "el gambiano", "MLI": "el maliense", "BFA": "el burkinés", "COD": "el congoleño", "GAB": "el gabonés",
    "EQG": "el ecuatoguineano", "CPV": "el caboverdiano", "SLE": "el sierraleonés", "DOM": "el dominicano",
    "CUB": "el cubano", "HON": "el hondureño", "CRC": "el costarricense", "PAN": "el panameño", "CAN": "el canadiense",
    "AUS": "el australiano", "NZL": "el neozelandés", "FIN": "el finlandés", "ISL": "el islandés", "WAL": "el galés",
    "NIR": "el norirlandés", "KVX": "el kosovar", "ARM": "el armenio", "RUS": "el ruso", "BUL": "el búlgaro",
}

# Porteros titulares seguros de 2024-25 ("el portero" / "el guardameta"): id -> True
TITULAR_GK = {
    "real-madrid/courtois", "atletico/oblak", "athletic/unai-simon", "real-sociedad/remiro", "valencia/mamardashvili",
    "espanyol/joan-garcia", "getafe/soria", "rayo/batalla", "leganes/dmitrovic", "alaves/sivera",
    "osasuna/sergio-herrera", "mallorca/leo-roman", "girona/gazzaniga", "villarreal/conde", "celta/villar",
}

# Posición fina y pie por jugador: "equipo/slug": ("POS", "pie")  -- se rellena en position_overrides.py (inline abajo)
EXTRA_ALIASES: dict[str, list[str]] = {   # apodos de narración habituales
    "barcelona/lewandowski": ["lewy", "robert lewandowski"], "barcelona/ter-stegen": ["ter stegen"],
    "barcelona/de-jong": ["frenkie", "de jong", "frenkie de jong"], "barcelona/lamine-yamal": ["lamine", "yamal"],
    "barcelona/inigo-martinez": ["inigo"], "barcelona/dani-olmo": ["olmo"], "barcelona/fermin-lopez": ["fermin"],
    "barcelona/ferran-torres": ["ferran"], "barcelona/cubarsi": ["pau cubarsi"],
        "barcelona/inaki-pena": ["inaki"], "barcelona/fati": ["ansu"],
    "real-madrid/vinicius": ["vini", "vinicius junior", "vini jr"], "real-madrid/mbappe": ["kylian"],
    "real-madrid/bellingham": ["jude"], "real-madrid/carvajal": ["dani carvajal"], "real-madrid/valverde": ["fede valverde", "fede"],
    "real-madrid/tchouameni": ["aurelien"], "real-madrid/camavinga": ["edu camavinga"], "real-madrid/rudiger": ["antonio rudiger"],
    "atletico/griezmann": ["grizi", "antoine"], "atletico/julian-alvarez": ["julian", "la arana"], "atletico/de-paul": ["rodrigo de paul"],
    "atletico/oblak": ["jan"], "atletico/simeone": ["giuliano", "el cholito"], "atletico/koke": [],
    "athletic/nico-williams": ["nico"], "athletic/inaki-williams": ["inaki"], "athletic/unai-simon": [],
    "real-sociedad/oyarzabal": ["oyarzabal"], "betis/isco": ["isco alarcon"], "betis/lo-celso": ["gio"],
    "celta/aspas": ["iago"], "mallorca/muriqi": ["vedat"],
}
ID_OVERRIDES: dict[str, str] = {}          # "equipo/slug_por_defecto" -> slug final
ACADEMY: set[str] = set()                  # ids con cantera conocida (además de los que Wikipedia marca "Youth system")

# ----------------------------------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------------------------------
def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm(s: str) -> str:
    s = strip_accents(s).lower().replace("ß", "ss").replace("ø", "o").replace("đ", "d").replace("ł", "l")
    s = s.replace("ı", "i").replace("æ", "ae").replace("œ", "oe").replace("þ", "th").replace("ð", "d")
    s = re.sub(r"[^a-z0-9 ]+", " ", s.replace("-", " "))
    return re.sub(r"\s+", " ", s).strip()


def slugify(s: str) -> str:
    return norm(s).replace(" ", "-")


def split_top(s: str, sep: str = "|") -> list[str]:
    """Divide por `sep` respetando [[ ]] y {{ }}."""
    parts, depth_b, depth_c, cur, i = [], 0, 0, [], 0
    while i < len(s):
        two = s[i:i + 2]
        if two == "[[":
            depth_b += 1; cur.append(two); i += 2; continue
        if two == "]]":
            depth_b -= 1; cur.append(two); i += 2; continue
        if two == "{{":
            depth_c += 1; cur.append(two); i += 2; continue
        if two == "}}":
            depth_c -= 1; cur.append(two); i += 2; continue
        if s[i] == sep and depth_b == 0 and depth_c == 0:
            parts.append("".join(cur)); cur = []
        else:
            cur.append(s[i])
        i += 1
    parts.append("".join(cur))
    return parts


def wl(text: str) -> tuple[str, str]:
    """[[Objetivo|Texto]] -> (objetivo, texto). Texto plano -> (texto, texto)."""
    text = re.sub(r"<ref.*?</ref>|<ref[^>]*/>|<!--.*?-->|<small>|</small>", "", text, flags=re.S).strip()
    text = re.sub(r"\{\{(?:small|nowrap)\|([^{}]*)\}\}", r"\1", text)
    m = re.search(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", text)
    if m:
        return m.group(1).strip(), (m.group(2) or m.group(1)).strip()
    m = re.search(r"\{\{(?:sortname|sort name)\|([^|}]+)\|([^|}]+)", text, flags=re.I)
    if m:
        full = f"{m.group(1)} {m.group(2)}".strip()
        return full, full
    t = re.sub(r"\{\{[^}]*\}\}", "", text).strip()
    return t, t


def display_name(text: str) -> str:
    """Quita desambiguaciones '(footballer, born 2000)' del texto mostrado."""
    return re.sub(r"\s*\((?:footballer|[^)]*born[^)]*)\)", "", text).strip()


# ----------------------------------------------------------------------------------------------------
# Parsers de plantilla
# ----------------------------------------------------------------------------------------------------
SKIP_HEAD = re.compile(r"loan|transfer|left|depart|former|released|staff|honours|statistics", re.I)
RESERVE_HEAD = re.compile(r"reserve|youth|b team|academy", re.I)


def parse_fs(text: str) -> list[dict]:
    """{{Fs player|no=..|pos=..|nat=..|name=..|other=..}} con seguimiento de secciones."""
    out, head = [], ""
    for line in text.splitlines():
        m = re.match(r"^=+\s*(.*?)\s*=+\s*$", line)
        if m:
            head = m.group(1)
            continue
        if not re.match(r"^\s*\{\{\s*Fs player", line, re.I):
            continue
        if SKIP_HEAD.search(head):
            continue
        body = line.strip()[2:-2] if line.strip().endswith("}}") else line.strip()[2:]
        args = split_top(body)[1:]
        kv = {}
        for a in args:
            if "=" in a:
                k, v = a.split("=", 1)
                kv[k.strip().lower()] = v.strip()
        link, shown = wl(kv.get("name", ""))
        if not shown:
            continue
        no = re.match(r"\d+", kv.get("no", ""))
        out.append(dict(link=link, shown=display_name(shown), number=int(no.group()) if no else None,
                        pos=kv.get("pos", "").upper()[:2], nat=kv.get("nat", "").upper(),
                        other=re.sub(r"\s+", " ", kv.get("other", "")), reserve=bool(RESERVE_HEAD.search(head)),
                        born=None, academy=False))
    return out


def parse_fbsi(text: str) -> list[dict]:
    """Barcelona: {{fb si player |n= |pos= |nb= |p= |age={{Age|Y|M|D|..}} |f=... |notes=...}}."""
    out, head = [], ""
    for line in text.splitlines():
        m = re.match(r"^=+\s*(.*?)\s*=+\s*$", line)
        if m:
            head = m.group(1)
            continue
        if "fb si player" not in line.lower():
            continue
        if SKIP_HEAD.search(head):
            continue
        body = line.strip()
        body = body[2:-2] if body.endswith("}}") else body[2:]
        kv = {}
        for a in split_top(body)[1:]:
            if "=" in a:
                k, v = a.split("=", 1)
                kv[k.strip().lower()] = v.strip()
        link, shown = wl(kv.get("p", ""))
        no = re.match(r"\d+", kv.get("n", ""))
        by = re.search(r"\{\{\s*Age\s*\|\s*(\d{4})", kv.get("age", ""), re.I)
        raw = line.lower()
        out.append(dict(link=link, shown=display_name(shown), number=int(no.group()) if no else None,
                        pos=kv.get("pos", "").upper()[:2], nat=kv.get("nb", "").upper(),
                        other=re.sub(r"\s+", " ", kv.get("notes", "")), reserve=bool(RESERVE_HEAD.search(head)),
                        born=int(by.group(1)) if by else None,
                        academy=("youth system" in raw or "la masia" in raw)))
    return out


def parse_table(text: str) -> list[dict]:
    """Tabla wiki (Valencia): filas con celdas No. | Pos. | Nat. | Player | Date of birth ..."""
    out, head = [], ""
    for block in re.split(r"\n\|-\s*\n", text):
        pass
    lines = text.splitlines()
    rows, cur, head = [], None, ""
    for ln in lines:
        m = re.match(r"^=+\s*(.*?)\s*=+\s*$", ln)
        if m:
            head = m.group(1)
        if ln.startswith("|-"):
            if cur is not None:
                rows.append((head, cur))
            cur = []
        elif cur is not None and ln.startswith("|") and not ln.startswith("|}"):
            cur.append(ln[1:].strip())
        elif ln.startswith("|}") and cur is not None:
            rows.append((head, cur)); cur = None
    for head, cells in rows:
        if len(cells) < 5 or SKIP_HEAD.search(head) or not re.match(r"^\d+", cells[0]):
            continue
        link, shown = wl(re.sub(r"^[^|\[]*\|\s*", "", cells[3]) if "[[" not in cells[3] else cells[3])
        pos = re.sub(r"\[\[[^\]|]*\|?([^\]]*)\]\]", r"\1", cells[1]).strip().upper()[:2]
        nat = re.search(r"flagicon\|([A-Z]{3})", cells[2])
        by = re.search(r"birth date(?: and age2?)?\|(?:\d+\|){3}(\d{4})", cells[4], re.I)
        out.append(dict(link=link, shown=display_name(shown), number=int(re.match(r"\d+", cells[0]).group()),
                        pos=pos, nat=nat.group(1) if nat else "", other="", reserve=bool(RESERVE_HEAD.search(head)),
                        born=int(by.group(1)) if by else None, academy=False))
    return out


def squad_from(tid: str) -> tuple[list[dict], str]:
    """Devuelve (jugadores, url_fuente)."""
    season = RAW / f"{tid}.wikitext"
    club = RAW / f"{tid}.club.wikitext"
    path = season
    text = season.read_text(encoding="utf-8") if season.exists() else ""
    players = []
    src = f"{WP}2024{D}25_{TEAMS[tid]['page'].replace(' ', '_')}_season"
    if "fb si player" in text.lower():
        players = parse_fbsi(text)
    elif re.search(r"\{\{\s*Fs player", text, re.I):
        players = parse_fs(text)
    if len(players) < 16 and "Fs player" not in text and season.exists() and "| Date of birth" in text:
        players = parse_table(text)
    # tabla (Valencia) más Fs player (reserva)
    if "| Date of birth" in text and "Fs player" in text:
        players = parse_table(text) + parse_fs(text)
    if len(players) < 16 and club.exists():
        ctext = club.read_text(encoding="utf-8")
        m = re.match(r"<!-- revid=(\d+)", ctext)
        players = parse_fs(ctext)
        src = f"https://en.wikipedia.org/w/index.php?title={CLUB_PAGE[tid].replace(' ', '_')}&oldid={m.group(1)}" if m else src
    return players, src


def play_text(tid: str) -> str:
    """Texto de la página de temporada donde aparecen jugadores que jugaron (resumen y competiciones),
    sin plantilla, fichajes ni tablas de estadísticas."""
    f = RAW / f"{tid}.wikitext"
    if not f.exists():
        return ""
    secs = re.split(r"\n(?==+[^=])", f.read_text(encoding="utf-8"))
    keep, on = [], False
    for sec in secs:
        h = sec.split("\n", 1)[0].strip("= \t").lower()
        if re.match(r"(season overview|summary|competitions|la liga|copa del rey|matches|league table|results)", h) or on:
            on = True
        if re.match(r"(statistics|milestones|awards|notes|references|players|transfers|management)", h):
            on = False
        if on or h.startswith(("august", "september", "october", "november", "december", "january", "february",
                               "march", "april", "may", "pre-season", "background")):
            keep.append(sec)
    return norm(" ".join(keep))


def infobox_meta(tid: str) -> tuple[str | None, str | None]:
    f = RAW / f"{tid}.wikitext"
    if not f.exists():
        return None, None
    t = f.read_text(encoding="utf-8")
    coach = stadium = None
    m = re.search(r"\|\s*manager\s*=\s*(.+)", t)
    if m:
        first = re.split(r"<br\s*/?>", m.group(1))[0]
        coach = display_name(wl(first)[1]) or None
    m = re.search(r"\|\s*stadium\s*=\s*(.+)", t)
    if m:
        stadium = display_name(wl(m.group(1))[1]) or None
    return coach, stadium


# ----------------------------------------------------------------------------------------------------
# Construcción de jugadores
# ----------------------------------------------------------------------------------------------------
def default_known_as(shown: str) -> str:
    """Nombre de narración: apellido salvo que sea muy corriente (entonces nombre + apellido)."""
    if shown in KNOWN_AS:
        return KNOWN_AS[shown]
    toks = shown.split()
    if len(toks) == 1:
        return shown
    # apellido = partículas + última palabra
    i = len(toks) - 1
    while i > 1 and toks[i - 1].lower() in PARTICLES:
        i -= 1
    if i > 0 and toks[i - 1].lower() in PARTICLES:
        i -= 1
    surname = " ".join(toks[i:])
    if len(toks) == 2 and norm(toks[1]) in COMMON_SURNAMES | COMMON_WORDS:
        return shown
    if norm(surname) in COMMON_SURNAMES | COMMON_WORDS:
        return " ".join(toks[max(0, i - 1):]) if i >= 1 else shown
    if i == 0:
        return shown
    return surname


def load_legacy_asr() -> dict[str, list[str]]:
    if not LEGACY.exists():
        return {}
    t = LEGACY.read_text(encoding="utf-8")
    m = re.search(r"window\.ASR_ALIAS\s*=\s*\{(.*?)\};", t, re.S)
    out = {}
    for km in re.finditer(r'"([^"]+)"\s*:\s*\[(.*?)\]', m.group(1) if m else "", re.S):
        out[km.group(1)] = re.findall(r'"([^"]+)"', km.group(2))
    return out


def load_truth_ids() -> dict[str, dict[int, tuple[str, str]]]:
    """team -> {dorsal: (id, known_as)} del partido de referencia."""
    if not TRUTH.exists():
        return {}
    d = json.loads(TRUTH.read_text(encoding="utf-8"))
    res: dict[str, dict] = {}
    for team, lu in d["lineups"].items():
        for grp in ("starting", "bench"):
            for p in lu.get(grp, []):
                if p.get("number") is not None:
                    res.setdefault(team, {})[p["number"]] = (p["id"], p.get("known_as", ""), p["name"], p.get("position"))
    return res


def load_born() -> dict[str, int]:
    f = RAW / "born.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def fetch_born(links: list[str], cache: dict) -> dict:
    """Año de nacimiento (Wikidata P569) para enlaces de Wikipedia; guarda raw/born.json en cada lote."""
    import subprocess, time, urllib.parse
    todo = [l for l in dict.fromkeys(links) if l and l not in cache]

    def get(url):
        for _ in range(3):
            out = subprocess.run(["curl", "-s", "-m", "60", "-A", "roster-builder/1.0", url], capture_output=True).stdout
            try:
                return json.loads(out)
            except Exception:
                time.sleep(8)
        return None

    for i in range(0, len(todo), 40):
        batch = todo[i:i + 40]
        q = ("https://en.wikipedia.org/w/api.php?action=query&redirects=1&prop=pageprops&ppprop=wikibase_item"
             "&format=json&titles=" + urllib.parse.quote("|".join(batch)))
        js = get(q)
        if not js:
            continue
        qd = js.get("query", {})
        alias = {}
        for lst in (qd.get("normalized", []), qd.get("redirects", [])):
            for e in lst:
                alias[e["from"]] = e["to"]
        item_of = {pg.get("title"): pg.get("pageprops", {}).get("wikibase_item") for pg in qd.get("pages", {}).values()}
        qids = [v for v in item_of.values() if v]
        time.sleep(2)
        born_of = {}
        if qids:
            js2 = get("https://www.wikidata.org/w/api.php?action=wbgetentities&props=claims&format=json&ids=" + "|".join(qids))
            for qid, ent in (js2 or {}).get("entities", {}).items():
                try:
                    t = ent["claims"]["P569"][0]["mainsnak"]["datavalue"]["value"]["time"]
                    born_of[qid] = int(t[1:5])
                except Exception:
                    pass
        for l in batch:
            t = l
            for _ in range(2):
                t = alias.get(t, t)
            qid = item_of.get(t)
            cache[l] = born_of.get(qid)
        (RAW / "born.json").write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
        time.sleep(2)
    return cache


def build_team(tid: str, born_cache: dict, truth: dict, legacy_asr: dict) -> dict | None:
    players_raw, src = squad_from(tid)
    if not players_raw:
        return None
    meta = TEAMS[tid]
    coach, stadium = infobox_meta(tid)
    if tid not in ("valladolid", "getafe", "leganes", "rayo") and not coach:
        coach = None
    # Si otro club de la lista dice "on loan from <este club>" por ese jugador, ya no es de aquí
    team_names = {norm(TEAMS[tid]["name"]), norm(TEAMS[tid]["short"]), norm(TEAMS[tid]["page"])}
    loaned_out = set()
    for other_tid in TEAMS:
        if other_tid == tid or not ((RAW / f"{other_tid}.wikitext").exists()):
            continue
        for q in squad_from(other_tid)[0]:
            m = re.search(r"on loan from \[\[([^\]|]+)(?:\|([^\]]+))?\]\]", q["other"])
            if m and (norm(m.group(1)) in team_names or norm(m.group(2) or "") in team_names):
                loaned_out.add(norm(q["shown"]))
    players_raw = [p for p in players_raw if norm(p["shown"]) not in loaned_out]
    # Filtrar altas posteriores a la temporada (p. ej. "from 1 June 2025") y reservas sin dorsal
    keep = []
    for p in players_raw:
        o = p["other"].lower()
        if re.search(r"from (?:1|\d{1,2}) (?:june|july) 2025|joins? .*2025", o):
            continue
        if p["reserve"] and p["number"] is None:
            continue
        keep.append(p)
    # Reserva/cantera: solo si aparece en el relato de la temporada, está en el partido de referencia
    # o el primer equipo es corto.
    n_first = sum(1 for p in keep if not p["reserve"])
    ptxt = play_text(tid)
    team_truth0 = truth.get(tid, {})
    final = []
    for p in keep:
        if p["reserve"]:
            sur = norm(p["shown"]).split()[-1]
            in_truth = p["number"] in team_truth0
            mentioned = bool(re.search(rf"\b{re.escape(sur)}\b", ptxt))
            if not (in_truth or mentioned or n_first < 22):
                continue
        final.append(p)
    keep = final
    # ids
    team_truth = truth.get(tid, {})
    seen_ids: dict[str, int] = {}
    players = []
    # apellidos de narración repetidos dentro del equipo -> nombre completo para ambos
    sur_count: dict[str, int] = {}
    for p in keep:
        k0 = norm(default_known_as(p["shown"])).split()[-1]
        sur_count[k0] = sur_count.get(k0, 0) + 1
    for p in keep:
        shown = p["shown"]
        t_id = team_truth.get(p["number"]) if p["number"] is not None else None
        if t_id and norm(t_id[2]).split()[-1] in norm(shown + " " + p["link"]):
            slug = t_id[0].split("/", 1)[1]
            known = KNOWN_AS.get(shown) or t_id[1] or default_known_as(shown)
        else:
            known = default_known_as(shown)
            if sur_count[norm(known).split()[-1]] > 1 and shown not in KNOWN_AS:
                known = shown
            slug = slugify(known)
        slug = ID_OVERRIDES.get(f"{tid}/{slug}", slug)
        pid = f"{tid}/{slug}"
        if pid in seen_ids:  # colisión: añade nombre completo
            slug = slugify(shown)
            pid = f"{tid}/{slug}"
            if pid in seen_ids:
                pid = f"{pid}-{p['number'] or len(seen_ids)}"
        seen_ids[pid] = 1
        line_code = LINE_CODE.get(p["pos"], "MID")
        pos, foot = POSITIONS.get(pid, (POS_BY_LINE.get(p["pos"], "CM"), "R"))
        pos = pos or POS_BY_LINE.get(p["pos"], "CM")
        if t_id and len(t_id) > 3 and t_id[3]:  # alineación real del partido de referencia
            pos = t_id[3]
        if LINE_OF[pos] != line_code and pid not in POSITIONS:
            pos = POS_BY_LINE.get(p["pos"], "CM")
        born = p["born"] or born_cache.get(p["link"])
        academy = p["academy"] or pid in ACADEMY
        player = dict(id=pid, team=tid, name=shown, known_as=known, number=p["number"], position=pos,
                      line=LINE_OF[pos], foot=foot, born=born, academy=academy, nationality=p["nat"],
                      aliases=[], asr_aliases=[], epithets=[], _link=p["link"])
        players.append(player)

    # alias
    surname_count: dict[str, int] = {}
    first_count: dict[str, int] = {}
    for pl in players:
        toks = norm(pl["known_as"]).split()
        surname_count[toks[-1]] = surname_count.get(toks[-1], 0) + 1
        ftoks = norm(pl["name"]).split()
        first_count[ftoks[0]] = first_count.get(ftoks[0], 0) + 1
    for pl in players:
        al: list[str] = []

        def add(a: str):
            a = norm(a)
            if a in COMMON_WORDS and " " not in a:  # palabra corriente suelta: solo formas compuestas
                return
            if a and a not in al:
                al.append(a)

        k = norm(pl["known_as"])
        full = norm(pl["name"])
        ktoks = k.split()
        add(k)
        add(full)
        # apellido suelto (solo si no es corriente, ni nombre de pila, ni único problema de duplicado)
        if len(ktoks) > 1:
            sur = ktoks[-1]
            if sur not in COMMON_SURNAMES | COMMON_WORDS | COMMON_FIRST and surname_count.get(sur, 0) == 1 \
                    and len(sur) > 3 and ktoks[-2] not in PARTICLES:
                add(sur)
        # nombre de pila solo con patrón de apodo + apellido corriente ("Kike Pérez" -> "kike")
        ftoks = full.split()
        if len(ktoks) > 1 and norm(pl["known_as"]).split()[0] == ftoks[0]:
            fn = ftoks[0]
            if fn not in COMMON_FIRST | COMMON_WORDS and first_count.get(fn, 0) == 1 and len(fn) >= 4 \
                    and norm(pl["known_as"]).split()[-1] in COMMON_SURNAMES:
                add(fn)
        # apellido con partículas sueltas ("jong" no; "de jong" sí ya incluido como known_as)
        for a in EXTRA_ALIASES.get(pl["id"], []):
            add(a)
        pl["aliases"] = al

    # asr_aliases desde legacy
    team_players_by_alias = {}
    for pl in players:
        for a in pl["aliases"] + [norm(pl["name"]), norm(pl["known_as"])]:
            team_players_by_alias.setdefault(a, pl)
    for key, variants in legacy_asr.items():
        nk = norm(key)
        target = team_players_by_alias.get(nk)
        if target is None:
            continue
        mine = set(target["aliases"]) | {norm(target["name"])}
        for v in variants:
            nv = norm(v)
            if nv and nv not in mine and nv not in target["asr_aliases"]:
                target["asr_aliases"].append(nv)

    # epítetos
    for pl in players:
        ep = []
        if pl["number"] is not None:
            ep.append(f"el {pl['number']}")
        dem = DEMONYM.get(pl["nationality"])
        if dem:
            ep.append(dem)
        if pl["academy"]:
            ep.append("el canterano")
        if pl["id"] in TITULAR_GK:
            ep += ["el portero", "el guardameta"]
        pl["epithets"] = ep
        del pl["_link"]

    c = meta["colors"]
    return dict(id=tid, name=meta["name"], short=meta["short"], aliases=[norm(a) for a in meta["aliases"]],
                colors=dict(primary=c[0], secondary=c[1], text=c[2]), coach=coach, stadium=stadium,
                verified=True, source=src, players=sorted(players, key=lambda x: (x["number"] is None, x["number"] or 0, x["id"])))


def main(argv: list[str]) -> int:
    truth = load_truth_ids()
    legacy = load_legacy_asr()
    born = load_born()
    if "--born" in argv:
        links = []
        for tid in TEAMS:
            if (RAW / f"{tid}.wikitext").exists():
                links += [p["link"] for p in squad_from(tid)[0] if p["born"] is None]
        born = fetch_born(links, born)
        print("born cache:", sum(1 for v in born.values() if v), "/", len(born))
    ids = [a for a in argv if not a.startswith("--")] or list(TEAMS)
    teams, missing = [], []
    for tid in TEAMS:  # orden alfabético por id de equipo
        if tid not in ids:
            continue
        t = build_team(tid, born, truth, legacy)
        if t is None:
            missing.append(tid)
            continue
        teams.append(t)
    # Mantener equipos ya presentes en el JSON si se construye solo un subconjunto
    if OUT.exists() and argv and not any(a == "--all" for a in argv):
        prev = {t["id"]: t for t in json.loads(OUT.read_text(encoding="utf-8"))["teams"]}
        prev.update({t["id"]: t for t in teams})
        teams = [prev[k] for k in TEAMS if k in prev]
    OUT.write_text(json.dumps({"season": "2024-25", "teams": teams}, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    n = sum(len(t["players"]) for t in teams)
    print(f"{len(teams)} equipos, {n} jugadores -> {OUT}")
    if missing:
        print("sin raw/plantilla:", ", ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
