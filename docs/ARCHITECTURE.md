# LaLiga Copilot v2 — Architecture

Status: **base design**. This document is the contract between the components: the interfaces and formats defined
here are not changed without updating this file.

## 1. Flow

```
 audio ──► AsrEngine ──► NLU ──► MatchContext ──► GraphicSelector ──► WebSocket ──► web
(mic or    (partial and  (entities,  (score, minute,   (which graphic,   /ws/operator   operator
 replay)    final text)   events,     subject,          with which data,  /ws/program    programme
                          roles,       templates,        priority, TTL)                   (1920×1080)
                          chains)      timeline)              ▲
                                                              │
                                                  DataProvider (synthetic | openfootball | licensed feed slot)
```

Everything travels on an **in-memory event bus** (`copilot/bus.py`, asyncio, publish/subscribe per topic). Each message
carries a `trace_id` and per-stage timestamps, so the latency from end-of-word to painted graphic is measured end to
end without separate instrumentation (`copilot/obs/`).

| Bus topic | Producer | Payload (`copilot/types.py`) |
|---|---|---|
| `audio.chunk` | audio source | PCM 16 kHz mono int16, `t_audio` (seconds since the source started) |
| `asr.partial` / `asr.final` | `AsrEngine` | `Transcript` |
| `nlu.result` | NLU | `NluResult` |
| `match.event` | `MatchContext` | `MatchEvent` (confirmed, de-duplicated event that enters the timeline) |
| `graphic.show` / `graphic.hide` | `GraphicSelector` or operator | `GraphicCommand` |
| `program.take` / `program.clear` | operator | `GraphicCommand` sent to the programme output |
| `obs.latency` | any | `StageTiming` |

## 2. Decisions and discarded alternatives

| Decision | Chosen | Discarded, and why |
|---|---|---|
| Backend language | **Python 3.12 + FastAPI + WebSocket** (uvicorn), a single process | Node: the good local speech engines on Apple Silicon (MLX, Whisper) and the data generator live in Python; two languages on the critical path add a process hop. Rust/Go: no measurable benefit for a sub-50 ms NLU. |
| NLU | **Deterministic Python** (gazetteer + phonetics + pattern catalogue + role linking + context), ported from `legacy/catalogo.js` | Keeping it in the browser (JS): it cannot be evaluated with `make eval` and cannot be shared with replay mode without a browser. An LLM on the critical path: latency and non-determinism. It would only be tried as a slow branch and included only if it improves the benchmark. |
| ASR | An `AsrEngine` interface with several implementations, chosen **with data** (see `FINAL_REPORT.md`). Candidates: `mlx-whisper` (sliding window + local agreement), `parakeet-mlx` (multilingual v3), Vosk Spanish (first pass), Web Speech (demo) | Cloud services (Deepgram, AssemblyAI): not zero cost. `whisper.cpp` is the fallback if MLX gives trouble. |
| Data | **Generated SQLite** (`data/synth/out/laliga-2024-25.sqlite`, not versioned, reproducible from a seed) behind the `DataProvider` interface | A huge JSON in memory: ~700 000 events with coordinates do not fit comfortably and are not queried well. Postgres: requires an installation; SQLite ships with Python. |
| Frontend | **React + TypeScript + Vite**, the pitch in SVG with `d3-scale`/`d3-shape`/`d3-contour` (no `d3-selection`: React paints), CSS with our own design tokens | Keeping a single HTML file: does not scale to 8+ graphic types or two views. Canvas: worse for declarative animation and for crisp text at 1080p; used only for the heat map if SVG is too slow. Generic charting libraries: they do not give a broadcast finish. |
| Images | An `ImageProvider` that generates **our own SVG** (silhouette + number + club colours, schematic crests) | Official photos and crests: copyright. |
| Replay | The backend reads a WAV at real-time speed and injects it as if it came from the microphone; the browser plays the same audio in sync. Also **replay from cached transcript** (deterministic, ×N) for `make eval` | Relying on the microphone for tests: not reproducible. |
| Configuration | `config/default.yaml` + optional `config/local.yaml` + `COPILOT_*` environment variables | Constants in code. |
| Legacy code | Moved to `legacy/` on this branch (unchanged on `main`) | Deleting it: loses the reference needed to measure "before and after". |

## 3. Repository structure

```
copilot/            Python package
  types.py          pydantic models for everything on the bus (the contract)
  bus.py            asyncio publish/subscribe
  config.py         YAML loading
  asr/              base.py (AsrEngine) + one module per engine + sources.py (microphone, file, replay)
  nlu/              normalize.py, entities.py, catalog.py, roles.py, context.py, modality.py, chains.py, engine.py
  match/            context.py (match state, timeline, de-duplication)
  graphics/         selector.py (which graphic), payloads.py (data for each graphic)
  data/             provider.py (DataProvider), synthetic.py, openfootball.py, images.py (ImageProvider)
  server/           app.py (FastAPI), ws.py
  obs/              latency.py (p50/p95 histograms per stage), logging
data/rosters/       real 2024-25 squads (JSON): public facts, the basis of everything
data/synth/         fictional data generator + plausibility tests
web/                frontend (React + TS + Vite): / (operator), /program (clean output), /replay
eval/               asr/ (local audio, reference), gold/ (gold annotations), scripts/, history/ (dated results)
tests/              pytest
legacy/             original prototype (reference only)
docs/               architecture and final report
```

## 4. Canonical identifiers

- Team: lowercase `slug` without accents: `barcelona`, `valladolid`, `real-madrid`, `atletico`…
- Player: `team/slug`: `barcelona/lamine-yamal`, `barcelona/lewandowski`, `valladolid/hein`.
- Match: `2024-25/J04/barcelona-valladolid`.
- Single source of truth: `data/rosters/2024-25.json`:

```json
{"season":"2024-25","teams":[{"id":"barcelona","name":"FC Barcelona","short":"Barça",
  "aliases":["barca","barcelona","azulgranas","culés","blaugrana"],
  "colors":{"primary":"#A50044","secondary":"#004D98","text":"#FFFFFF"},
  "players":[{"id":"barcelona/lamine-yamal","name":"Lamine Yamal","known_as":"Lamine","number":19,
    "position":"RW","line":"FWD","foot":"L","born":2007,"academy":true,"nationality":"ESP",
    "aliases":["lamine","yamal","lamine yamal"],
    "asr_aliases":["lamin","la mine","alain","minia"],
    "epithets":["el canterano","el 19","el de Rocafonda"]}]}]}
```

`position` ∈ GK, RB, CB, LB, DM, CM, AM, RW, LW, ST. `line` ∈ GK, DEF, MID, FWD.

## 5. Data contracts (summary; the executable definition is `copilot/types.py`)

### Transcript
```json
{"trace_id":"…","engine":"mlx-whisper-turbo","final":true,"text":"gol de Raphinha",
 "t0":1203.4,"t1":1205.1,
 "words":[{"w":"gol","t0":1203.4,"t1":1203.7,"p":0.98}],
 "ts":{"audio_end":…, "asr_emit":…}}
```
`t0/t1` are seconds of audio since the source started. `ts.*` are server monotonic-clock timestamps (ms).

### NluResult
```json
{"trace_id":"…","text":"…","t0":…,"t1":…,
 "entities":[{"type":"player","id":"barcelona/raphinha","span":[2,3],"surface":"rafiña","score":0.93,"via":"asr_alias"}],
 "events":[{"type":"gol","fine":"gol","modality":"real","roles":{"actor":"barcelona/raphinha"},
            "span":[0,1],"chain":null,"order":0,"confidence":0.9}],
 "intents":[{"type":"stat_query","topic":"goles","subject":"barcelona/raphinha"}],
 "ts":{"nlu_in":…, "nlu_out":…}}
```

- `via` ∈ `exact | alias | asr_alias | phonetic | fuzzy | epithet | coref | number`.
- `modality` ∈ `real | negated | hypothetical | query | past` (`past` = something is said about another match or an
  earlier time: "he scored three last week"). **Only `real` enters the timeline and counts for event cards.**
- `roles`: keys `actor`, `receiver` (recipient of a pass, cross or assist), `victim` (who is fouled, dribbled past,
  saved…), `out` (who leaves in a substitution; `actor` = who comes on), `team_for`, `team_against` (only when no
  player can be resolved). Values are canonical ids. For cards, `actor` = the player booked.
- `Transcript.segment_id` groups the partial results of the same stretch; `stable_upto` = number of words that will
  no longer change.
- Speech engines run on their own thread (their `feed` blocks); `analyze(final=False)` does not touch the context.
- All aggregate methods of `DataProvider` accept `until` (match or matchday): during a live broadcast of matchday 4,
  only what happened before matchday 4 is shown.

### Event types (coarse taxonomy, the one that is evaluated)
`gol, tiro, parada, palo, ocasion, pase, centro, asistencia, regate, falta, penalti, mano, corner, saque_banda,
saque_puerta, fuera_juego, amarilla, roja, cambio, lesion, robo, perdida, despeje, var, inicio, descanso, final`.

`fine` keeps the fine-grained catalogue id (e.g. `penalti_parado`, `gol_anulado`, `remate_cabeza`); the catalogue
declares which coarse type each one belongs to. Cases that change coarse type: `gol_anulado` → `gol` with
`modality:"negated"`; `penalti_no` → `penalti` with `modality:"negated"`.

### MatchEvent (timeline)
```json
{"id":"ev-0042","t_audio":1204.2,"minute":20,"period":1,"type":"gol","fine":"gol","roles":{"actor":"barcelona/raphinha"},
 "team":"barcelona","source":"nlu","status":"auto","confidence":0.9,"text":"gol de Raphinha","trace_id":"…"}
```
`status` ∈ `auto | approved | edited | discarded` (changed by the operator). `source` ∈ `nlu | operator | feed`.

### GraphicCommand
```json
{"id":"g-0102","kind":"player_card","priority":70,"ttl_ms":12000,"pinned":false,
 "reason":{"trigger":"event:gol","trace_id":"…","text":"gol de Raphinha"},
 "payload":{…depends on kind…},"demo_data":true,
 "ts":{"audio_end":…,"asr_emit":…,"nlu_out":…,"select_out":…,"ws_send":…}}
```
`kind` ∈ `player_card | pass_network | connection | shot_map | heat_map | comparison | standings | h2h | team_card |
situation | timeline | scorebug`. `demo_data:true` forces the **"Datos de demostración"** badge to be painted.
The frontend answers over the WebSocket with `{"type":"painted","id":"g-0102","t_paint":…}` (after
`requestAnimationFrame`), which closes the latency measurement.

## 6. Interfaces

```python
class AsrEngine(Protocol):
    name: str
    def start(self, *, prompt: str, vocabulary: list[str], language: str = "es") -> None: ...
    def feed(self, pcm16: bytes, t_audio: float) -> list[Transcript]: ...   # partial and final results available
    def flush(self) -> list[Transcript]: ...
    def close(self) -> None: ...

class NluEngine(Protocol):
    def analyze(self, text: str, *, t0: float, t1: float, final: bool, ctx: "MatchContext") -> NluResult: ...

class DataProvider(Protocol):
    synthetic: bool                                        # True → the UI shows "Datos de demostración"
    def teams(self, season: str) -> list[Team]: ...
    def squad(self, team_id: str, season: str) -> list[Player]: ...
    def standings(self, season: str, until_round: int | None = None) -> list[StandingRow]: ...
    def matches(self, season: str, team_id: str | None = None) -> list[MatchInfo]: ...
    def player_season(self, player_id: str, season: str) -> PlayerSeason: ...       # aggregates + percentiles by position
    def team_season(self, team_id: str, season: str) -> TeamSeason: ...
    def events(self, match_id: str | None = None, *, player_id=None, team_id=None, types=None, season=None) -> list[PitchEvent]: ...
    def pass_network(self, team_id: str, *, match_id: str | None = None, season: str | None = None) -> PassNetwork: ...
    def connection(self, a: str, b: str, *, season: str) -> Connection: ...
    def h2h(self, team_a: str, team_b: str) -> H2H: ...

class ImageProvider(Protocol):
    def player_avatar(self, player_id: str, *, size: int = 512) -> str: ...   # SVG
    def team_crest(self, team_id: str, *, size: int = 256) -> str: ...        # SVG
```

Pitch coordinates: **105 × 68 m**, origin at the bottom-left corner. The home team always attacks towards increasing
x (the frontend flips the view when needed).

Provider composition: `CompositeProvider` (openfootball for real results and standings, synthetic for everything
else). A documented slot in `copilot/data/licensed.py` (Opta / StatsBomb / API-Football) implements the same interface.

## 7. NLU: critical path design (< 50 ms)

1. **Normalisation** (`normalize.py`): lowercase, no accents, ñ→n, numbers ("el nueve" → 9), tokenisation with offsets.
2. **Entities** (`entities.py`): an automaton over the gazetteer of the **match in progress** (22–40 players plus the
   coaching staff) and, with lower priority, the rest of the league. Order: exact → alias → ASR alias → Spanish phonetics
   (b/v, c/k/q, ll/y, silent h, s/z/c, g/j) → bounded Levenshtein, excluding the 15 000 most common words
   (`legacy/comunes.js`) unless there is an explicit alias. Repeated surnames are disambiguated by the match in
   progress, the team in possession and the last mentioned player.
3. **Situation catalogue** (`catalog.py`): a port of `legacy/catalogo.js` (patterns, `refines`, known vetoes) with the
   coarse type for each situation. The data lives in YAML (`copilot/nlu/catalog.yaml`) so it can be reviewed without
   touching code.
4. **Roles** (`roles.py`): prepositions and verbs (sobre/para/de/a/por, passive voice, victim verbs), plus per-verb
   frames for chains ("abre a la banda para X", "se va de Y", "la pone al segundo palo").
5. **Context and coreference** (`context.py`): current subject, last entity per type/team, epithets ("el canterano",
   "el 9", "el polaco", "su compañero", "el portero" → resolved by line-up and position), ellipsis ("y marca").
6. **Modality** (`modality.py`): negation ("no era penalti"), hypotheticals ("si marca…", "podría", "ojalá"), data
   requests ("¿cuántos lleva?"), past and other matches ("la semana pasada", "el año pasado").
7. **Chains** (`chains.py`): consecutive events in the same sentence or window where the receiver of one is the actor
   of the next are linked (`chain`, `order`).
8. **Stability with partial results**: partial results can only *propose* an entity graphic (a player card); events are
   confirmed on the final result or once a partial has been stable for two updates (this avoids a premature "penalty…
   on Lamine").

Optional slow branch (never blocks): a small local model for sentences the fast path marks as `low_confidence`. It is
only integrated if it improves both dev **and** test in `make eval`.

## 8. Evaluation (`make eval`)

### Gold format (`eval/gold/*.jsonl`, one sentence per line)
```json
{"id":"bv-1h-0123","split":"dev","source":"audio","match":"2024-25/J04/barcelona-valladolid",
 "t0":1203.4,"t1":1207.9,"text":"gol de Raphinha, qué pase de Lamine",
 "prev":["la tiene Lamine en banda derecha"],
 "entities":[{"surface":"Raphinha","type":"player","id":"barcelona/raphinha"},
             {"surface":"Lamine","type":"player","id":"barcelona/lamine-yamal"}],
 "events":[{"type":"asistencia","modality":"real","roles":{"actor":"barcelona/lamine-yamal","receiver":"barcelona/raphinha"},"chain":"c1","order":1},
           {"type":"gol","modality":"real","roles":{"actor":"barcelona/raphinha"},"chain":"c1","order":2}],
 "group":null,"reviewed":true,"doubt":null,"preannotated_by":null,"tags":["chain"]}
```
- `source` ∈ `audio | echoes | catalog | hard`. `split` ∈ `dev | test`.
- **Split.** Real audio: **first half → dev, second half → test** (from `meta.json`). Everything else carries a `group`
  (template, match or case family) and is split by a stable hash of the **group** (≈60/40), so that variants of the same
  template never fall on both sides.
- **The test split is frozen** before the engine is written: `eval/gold/TEST_MANIFEST.sha256` (checked by `make eval`).
- **What counts for acceptance:** `reviewed` rows without `doubt` from `audio`, `echoes` and `hard`. `catalog` is drawn
  from the same catalogue that is ported to the engine (scoring well there is circular), so it is reported separately.
- `prev` provides context for coreference (passed to the engine before the sentence, not scored).
- Annotation rules and validator: `python -m eval.gold_tools validate`.
- No ASR alias or rule may come from looking at the second half of the audio. Hand-added `asr_aliases` carry their
  provenance in the commit.
- Ground truth for the match: `eval/gold/barca-valladolid.truth.json`.

### Metrics (exact definitions, not negotiable after the fact)
| Metric | Definition |
|---|---|
| **Entity F1** | micro-F1 over the set `{(type,id)}` per sentence (a repeated entity counts once). |
| **Events + roles F1** | micro-F1 over the **multiset** of tuples `(type, modality, actor ∥ team_for, receiver ∥ victim ∥ out)`. Emitting a negated event as `real` is both a false positive **and** a false negative. |
| **Chains** | % of gold chains of 2–3 events for which a predicted chain exists with **exactly** the same sequence of tuples (one-to-one matching; repeated `order` values invalidate the chain). Chain **precision** (predicted chains that exist in the gold) is also reported. |
| **Real match** | In replay of the full audio: every goal (scorer) and every substitution (on, off) in `truth.json` must have a `real` `MatchEvent` with the same roles within ±120 s of when it is narrated. Detected/total per type **and per half**; the second-half detail is only shown with `--split test`. |
| **False positives** | An erroneous card = a `graphic.show` whose trigger (word and time, via `trace_id`) does not match the gold: for player cards, the same entity mentioned within ±3 s; for events, the same tuple within ±5 s. **Any card withdrawn after a correction also counts** (shown from a partial and not confirmed). Reported per 10 minutes of **reviewed** audio, next to the total number of cards per 10 minutes. |
| **ASR WER** | `jiwer` with Spanish normalisation over reviewed stretches of the reference. |
| **ASR names (NER-ER)** | `(S + D + I) / N_ref`: one-to-one matching within ±1.5 s between name mentions in the reviewed reference and in the hypothesis, both resolved with **exact + canonical aliases only (no `asr_aliases`, no phonetics)**. S = another entity in that slot; D = reference mention with no partner; I = hypothesis mention with no partner (names invented by the prompt). The figure after the full linker is reported separately. The reference is reviewed **by listening** to at least two 10-minute stretches per half, because reading does not reveal the names Whisper omitted. |
| **Latency** | p50/p95 of `t_paint − audio_end`, where `audio_end` is the end of the trigger word **according to the reference alignment** (never the engine's own timestamps) and `t_paint` comes on the server clock after synchronising clocks with the browser. Replay at real-time speed with the speech engine running (never with cached transcripts). Reported separately for **player card (partial)** and **event (confirmed)**, and per stage: ASR, NLU, selector, network, paint. |
| **Data** | plausibility and event↔aggregate consistency tests (pytest) green. |

**On latency (known risk).** Whisper is not a streaming engine: the encoder processes 30 s, and in a sliding window a
word appears after "step + inference" (≈0.7–1.1 s at p95). That is why the fast path is designed as follows:
(a) a true streaming engine as a first pass (candidates: `parakeet-mlx`, Vosk with a name grammar) for player cards and
event keywords; (b) Whisper corrects afterwards; (c) an event may be shown on the first partial and withdrawn if the final
result does not confirm it (that withdrawal counts as a false positive); (d) VAD before the engine. Decided with
measurements.

`make eval` prints the table, saves it to `eval/history/AAAA-MM-DD_HHMMSS_<split>.{json,md}` and compares it with the
previous run. `dev` is the default; `test` is only run for reports, and its errors are never inspected sentence by
sentence.

## 9. Operator console and programme output

- `/` (operator): live transcript, queue of proposed graphics (approve / pin / discard / send to air), editable timeline,
  latency panel and engine status.
- `/program`: 1920×1080, `background: transparent`, no controls; it only paints what it receives through
  `program.take`. Optional automatic mode (whatever the selector marks with a priority above the threshold goes to air
  without an operator).
- Keyboard shortcuts for the operator; everything the operator does is logged as an event (`source:"operator"`).

## 10. Resilience and observability

- `AsrSupervisor`: if the main engine throws an exception or exceeds its latency budget N times, it switches to the
  backup engine and publishes this on `obs.status`. The same pattern applies to `DataProvider` (if the synthetic
  database has not been generated, the app still starts with openfootball and shows a warning).
- `GET /api/health`, `GET /api/metrics` (histograms per stage), structured JSON logging.

## 11. Commands

| Command | What it does |
|---|---|
| `make dev` | `scripts/bootstrap.sh` (uv, Node, ffmpeg, dependencies; no sudo) + generates data if missing + starts backend and frontend |
| `make test` | pytest + frontend tests |
| `make eval` | metrics table → `eval/history/` (needs the private evaluation data) |
| `make data` | regenerates the synthetic data (fixed seed) |
| `make reference` | reference transcription of the audio (heavy process; one at a time) |
