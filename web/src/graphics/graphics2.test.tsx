import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { GRAPHIC_KINDS, type GraphicKind, type TimelineItem } from "../contracts";
import { ImageSourceProvider } from "../design";
import { FIXTURES } from "../fixtures";
import { Gallery } from "../routes/Gallery";
import { Comparison } from "./Comparison";
import { Connection } from "./Connection";
import { eventKind } from "./EventIcon";
import { H2H, resultFor } from "./H2H";
import { HeatMap } from "./HeatMap";
import { PassNetwork, networkArrows, visibleEdges } from "./PassNetwork";
import { FORMAT, GRAPHICS, PLACEMENT, REPLAY_OR_BREAK_ONLY, STATUS } from "./registry";
import { Scorebug, minuteText } from "./Scorebug";
import { ShotMap } from "./ShotMap";
import { Situation } from "./Situation";
import { TeamCard } from "./TeamCard";
import { AXIS_W, Timeline, layoutSide } from "./Timeline";
import { GraphicView } from "./GraphicFrame";
import { fmtDate, surname } from "./shared";

const wrap = (ui: React.ReactElement) => <ImageSourceProvider mode="generated">{ui}</ImageSourceProvider>;

describe("los 12 grafismos", () => {
  it("todos están terminados y registrados", () => {
    for (const k of GRAPHIC_KINDS) {
      expect(STATUS[k]).toBe("done");
      expect(PLACEMENT[k]).toBeDefined();
    }
  });

  it("el marcador va en top 64 y ningún grafismo de arriba pisa su franja (hasta y 200)", () => {
    expect(PLACEMENT.scorebug).toEqual({ left: 64, top: 64 });
    for (const k of GRAPHIC_KINDS) {
      const top = (PLACEMENT[k] as { top?: number }).top;
      if (k !== "scorebug" && top != null) expect(top).toBeGreaterThanOrEqual(200);
    }
  });

  it("tres formatos de panel: cada grafismo usa uno y los de pantalla completa son solo repetición/descanso", () => {
    expect(new Set(Object.values(FORMAT))).toEqual(new Set(["lower", "half", "full", "scorebug"]));
    expect(REPLAY_OR_BREAK_ONLY).toEqual(["pass_network", "standings"]);
  });

  it.each(GRAPHIC_KINDS)("%s: pinta con su fixture y respeta el distintivo de demostración", (kind: GraphicKind) => {
    const C = GRAPHICS[kind] as React.ComponentType<{ payload: unknown; demoData: boolean }>;
    const { unmount } = render(wrap(<C payload={FIXTURES[kind]} demoData />));
    expect(screen.getAllByTestId("demo-badge")).toHaveLength(1);
    expect(screen.getByTestId("demo-badge")).toHaveTextContent(/datos de demostración/i);
    unmount();
    render(wrap(<C payload={FIXTURES[kind]} demoData={false} />));
    expect(screen.queryByTestId("demo-badge")).toBeNull();
  });
});

describe("helpers", () => {
  it("surname y fmtDate", () => {
    expect(surname({ known_as: "Íñigo Martínez" })).toBe("Martínez");
    expect(surname({ known_as: "De Jong" })).toBe("De Jong");
    expect(surname({ known_as: "Pedri" })).toBe("Pedri");
    expect(fmtDate("2025-01-12")).toBe("12 ene 2025");
  });
});

describe("PassNetwork", () => {
  it("11 nodos con dorsal y apellido; una flecha por arista que supera min_passes", () => {
    const { container } = render(wrap(<PassNetwork payload={FIXTURES.pass_network} demoData />));
    expect(container.querySelectorAll("[data-node]")).toHaveLength(11);
    // los pares de ida y vuelta (sin la conexión destacada) se funden en una sola línea
    const { arrows } = networkArrows(FIXTURES.pass_network, () => 0);
    expect(arrows.length).toBeLessThan(FIXTURES.pass_network.edges.length);
    expect(container.querySelectorAll("[data-arrow]")).toHaveLength(arrows.length);
    expect(screen.getByText("Martínez")).toBeInTheDocument();
    expect(screen.getByText(FIXTURES.pass_network.headline!)).toBeInTheDocument();
    expect(screen.getByTestId("pn-legend")).toBeInTheDocument();
    expect(screen.queryByText(/Solo parejas con/)).toBeNull(); // nota de metodología fuera de antena
  });

  it("sube min_passes → desaparecen las aristas flojas", () => {
    const p = { ...structuredClone(FIXTURES.pass_network), min_passes: 20 };
    const { container } = render(wrap(<PassNetwork payload={p} demoData />));
    const expected = p.edges.filter((e) => e.count >= 20).length;
    expect(expected).toBeLessThan(p.edges.length);
    expect(container.querySelectorAll("[data-arrow]")).toHaveLength(networkArrows(p, () => 0).arrows.length);
    expect(visibleEdges(p)).toHaveLength(expected);
  });

  it("el nodo con más pases es el más grande y la arista destacada va a pleno color", () => {
    const { container } = render(wrap(<PassNetwork payload={FIXTURES.pass_network} demoData />));
    const r = (id: string) => Number(container.querySelector(`[data-node="${id}"]`)!.getAttribute("data-r"));
    expect(r("barcelona/de-jong")).toBeGreaterThan(r("barcelona/lewandowski"));
    const hl = [...container.querySelectorAll("[data-arrow]")].filter((g) => g.getAttribute("opacity") === "1");
    expect(hl).toHaveLength(1);
    // destacada: color del club con contorno blanco (dos trazos superpuestos) y con punta
    expect(hl[0]!.getAttribute("data-highlight")).toBe("true");
    expect(hl[0]!.querySelectorAll("path")).toHaveLength(2);
    expect(hl[0]!.querySelector("polygon")).not.toBeNull();
  });

  it("menos ruido en el centro: pares fundidos y flechas menores de 14 pases sin punta; solo las importantes llevan punta", () => {
    const { arrows } = networkArrows(FIXTURES.pass_network, () => 0);
    const heads = arrows.filter((a) => !a.noHead);
    expect(heads.length).toBeLessThan(arrows.length);
    for (const a of heads) expect(a.highlight || a.count! >= 14).toBe(true);
    // un par fundido suma sus dos sentidos (De Jong ↔ Pedri: 26 + 20)
    expect(arrows.some((a) => a.count === 46 && a.noHead)).toBe(true);
  });

  it("la leyenda dibuja los mismos trazos que el campo: blanco al 55 % y la conexión destacada", () => {
    render(wrap(<PassNetwork payload={FIXTURES.pass_network} demoData />));
    expect(screen.getByTestId("pn-legend-hl")).toHaveTextContent("Conexión destacada");
    const lines = screen.getByTestId("pn-legend").querySelectorAll<HTMLElement>(".lg__line:not(.lg__line--hl)");
    for (const l of lines) expect(l.style.opacity).toBe("0.55");
  });

  it("las etiquetas de nodo llevan placa oscura propia (no heredan la opacidad del nodo)", () => {
    const { container } = render(wrap(<PassNetwork payload={FIXTURES.pass_network} demoData />));
    const labels = container.querySelectorAll("[data-label]");
    expect(labels).toHaveLength(11);
    for (const l of labels) {
      expect(l.querySelector("rect")!.getAttribute("fill")).toBe("rgba(5,8,14,0.72)");
      expect(l.querySelector("rect")!.getAttribute("rx")).toBe("6");
    }
  });
});

describe("Connection", () => {
  it("cifras A→B y B→A en blanco, pases clave, asistencias y leyenda con los trazos del campo; sin banda de socio", () => {
    const { container } = render(wrap(<Connection payload={FIXTURES.connection} demoData />));
    expect(screen.getByTestId("cn-ab")).toHaveTextContent("187");
    expect(screen.getByTestId("cn-ba")).toHaveTextContent("96");
    expect(screen.queryByText(/Socio/i)).toBeNull();
    // el receptor va sólido (100 %) y pintado después de las flechas
    const recv = container.querySelector(`[data-node="${FIXTURES.connection.b.id}"]`)!;
    expect(recv.querySelector('g[opacity="0.55"]')).toBeNull();
    const order = [...container.querySelectorAll("[data-layer]")].map((l) => l.getAttribute("data-layer"));
    expect(order.indexOf("arrows")).toBeLessThan(order.indexOf("nodes"));
    // "18 últimos pases" va en la banda del campo, no en la leyenda
    expect(screen.getByTestId("cn-sample")).toHaveTextContent("18 últimos pases");
    expect(screen.getByTestId("cn-legend")).not.toHaveTextContent(/últimos/);
    // paleta única: nada de turquesa; asistencia dorada y pase clave blanco
    expect(container.innerHTML).not.toMatch(/7cf0d0/i);
    expect(container.querySelector('[data-arrow="assist"] path:last-of-type')!.getAttribute("stroke")).toBe("#ffd23f");
    const legend = screen.getByTestId("cn-legend").querySelectorAll("i");
    expect(legend).toHaveLength(3);
    expect(screen.getAllByTestId("stat-tile")).toHaveLength(2);
    expect(container.querySelectorAll("[data-node]")).toHaveLength(2);
    expect(container.querySelectorAll("[data-arrow]")).toHaveLength(FIXTURES.connection.arrows.length);
    for (const k of ["pass", "key_pass", "assist"]) expect(container.querySelector(`[data-arrow="${k}"]`)).not.toBeNull();
  });
});

describe("ShotMap", () => {
  it("un círculo por tiro, goles rellenos, totales y leyendas", () => {
    const { container } = render(wrap(<ShotMap payload={FIXTURES.shot_map} demoData />));
    expect(container.querySelectorAll("circle[data-shot]")).toHaveLength(FIXTURES.shot_map.shots.length);
    const outcomes = new Set([...container.querySelectorAll("circle[data-shot]")].map((c) => c.getAttribute("data-shot")));
    expect(outcomes).toEqual(new Set(["goal", "saved", "off", "blocked", "post"]));
    const styles = new Set([...container.querySelectorAll("circle[data-shot]")].map((c) => `${c.getAttribute("stroke")}|${c.getAttribute("stroke-dasharray")}`));
    expect(styles.size).toBeGreaterThanOrEqual(4); // estilos distintos por resultado
    expect(screen.getAllByTestId("stat-tile")).toHaveLength(3); // tiros · goles · xG: nada más para 10 segundos
    expect(screen.queryByText(/xG\/tiro/)).toBeNull();
    const legend = within(screen.getByTestId("sm-outcomes"));
    expect(legend.getByText("Parado")).toBeInTheDocument();
    expect(screen.getByTestId("sm-xg-legend")).toBeInTheDocument();
  });

  it("el recuento por resultado de la leyenda suma los tiros", () => {
    render(wrap(<ShotMap payload={FIXTURES.shot_map} demoData />));
    const sum = [...screen.getByTestId("sm-outcomes").querySelectorAll("b")].reduce((s, b) => s + Number(b.textContent), 0);
    expect(sum).toBe(FIXTURES.shot_map.shots.length);
  });
});

describe("HeatMap", () => {
  it("capa de calor, flecha de ataque, total con separador de millares y zonas", () => {
    const { container } = render(wrap(<HeatMap payload={FIXTURES.heat_map} demoData />));
    expect(container.querySelector('[data-layer="heat"]')).not.toBeNull();
    expect(container.querySelector('[data-layer="attack-arrow"]')).not.toBeNull();
    expect(screen.getByTestId("hm-total")).toHaveTextContent("1.842");
    expect(within(screen.getByTestId("hm-zones")).getAllByRole("listitem")).toHaveLength(3);
    expect(screen.getByText(/Toques en total/i)).toBeInTheDocument();
  });
});

describe("Comparison", () => {
  it("una fila por métrica, mejor resaltado según `better`", () => {
    const { container } = render(wrap(<Comparison payload={FIXTURES.comparison} demoData />));
    const rows = screen.getAllByTestId("cm-row");
    expect(rows).toHaveLength(6);
    const goals = rows[0]!;
    expect(goals).toHaveAttribute("data-better", "b");
    expect(goals.querySelector(".cm__val--b")).toHaveClass("is-best");
    expect(goals.querySelector(".cm__val--a")).not.toHaveClass("is-best");
    expect(rows[1]!.querySelector(".cm__val--a")).toHaveClass("is-best");
    expect(container.querySelectorAll(".cm__bar i")).toHaveLength(12);
  });

  it("`better: tie` resalta ambos", () => {
    const p = structuredClone(FIXTURES.comparison);
    p.rows[0]!.better = "tie";
    render(wrap(<Comparison payload={p} demoData />));
    const r = screen.getAllByTestId("cm-row")[0]!;
    expect(r.querySelectorAll(".is-best").length).toBe(4);
  });

  it("la barra del mayor ocupa el 100 % y la otra es proporcional", () => {
    const { container } = render(wrap(<Comparison payload={FIXTURES.comparison} demoData />));
    const bars = container.querySelectorAll(".cm__row")[0]!.querySelectorAll(".cm__bar i");
    expect((bars[1] as HTMLElement).style.width).toBe("100%");
    expect(parseFloat((bars[0] as HTMLElement).style.width)).toBeCloseTo((8 / 14) * 100, 0);
  });
});

describe("H2H", () => {
  it("variante live (tercio inferior): balance, barra proporcional y goles integrados; sin lista de partidos", () => {
    const { container } = render(wrap(<H2H payload={FIXTURES.h2h} demoData />));
    expect(screen.getByTestId("h2h-a")).toHaveTextContent("5");
    expect(screen.getByTestId("h2h-d")).toHaveTextContent("2");
    expect(screen.getByTestId("h2h-b")).toHaveTextContent("1");
    const segs = [...container.querySelectorAll("[data-seg]")].map((s) => Number(s.getAttribute("data-n")));
    expect(segs).toEqual([5, 2, 1]);
    // la barra es estrictamente proporcional (sin mínimo); el mínimo de 160 px es solo de las cifras
    expect((screen.getByTestId("h2h-bar") as HTMLElement).style.gridTemplateColumns).toBe("5fr 2fr 1fr");
    expect((container.querySelector(".h2h__hero") as HTMLElement).style.gridTemplateColumns).toBe("minmax(160px, 5fr) minmax(160px, 2fr) minmax(160px, 1fr)");
    expect(screen.getByTestId("h2h-goals")).toHaveTextContent("17");
    expect(container.querySelector(".panel--lower")).not.toBeNull();
    expect(screen.queryByTestId("h2h-last")).toBeNull();
    expect(screen.queryByText(/Resultado para/)).toBeNull();
  });

  it("variante full (medio panel): últimos partidos solo con abreviaturas, raya – y sin temporada repetida", () => {
    const { container } = render(wrap(<H2H payload={FIXTURES.h2h} demoData variant="full" />));
    expect(container.querySelector(".panel--half")).not.toBeNull();
    const matches = screen.getAllByTestId("h2h-match");
    expect(matches).toHaveLength(5);
    expect(matches[0]).toHaveTextContent("12 ene 2025");
    expect(matches[0]).toHaveTextContent("3 – 1");
    expect(matches[0]).not.toHaveTextContent(/LaLiga/);
    expect(matches[2]!.querySelector(".h2h__chip")).toHaveAttribute("data-result", "D");
    expect(container.querySelectorAll(".h2h__m img, .h2h__m svg")).toHaveLength(0); // sin minicrestas por fila
  });

  it("resultFor calcula V/E/D desde el punto de vista de A, local o visitante", () => {
    const [m1, m2, m3] = FIXTURES.h2h.last;
    expect(resultFor(m1!, FIXTURES.h2h.a)).toBe("W");
    expect(resultFor(m2!, FIXTURES.h2h.a)).toBe("W"); // el Barça gana de visitante
    expect(resultFor(m3!, FIXTURES.h2h.a)).toBe("D");
  });

  it("sin empates no pinta el segmento vacío", () => {
    const p = { ...structuredClone(FIXTURES.h2h), draws: 0 };
    const { container } = render(wrap(<H2H payload={p} demoData />));
    expect(container.querySelectorAll("[data-seg]")).toHaveLength(2);
  });
});

describe("TeamCard", () => {
  it("tercio inferior: nombre, LÍDER, puntos, forma y 4 tiles sin barras de percentil", () => {
    const { container } = render(wrap(<TeamCard payload={FIXTURES.team_card} demoData />));
    expect(container.querySelector(".panel--lower")).not.toBeNull();
    expect(screen.getByRole("heading", { name: "FC Barcelona" })).toBeInTheDocument();
    expect(screen.getByTestId("tc-pos")).toHaveTextContent("LÍDER");
    expect(screen.queryAllByTestId("percentile-bar")).toHaveLength(0);
    expect(screen.getByTestId("tc-pts")).toHaveTextContent("70");
    expect(screen.getAllByTestId("stat-tile")).toHaveLength(4);
    expect(screen.getByRole("img", { name: /Forma/ })).toBeInTheDocument();
  });

  it("posición distinta de 1: \"3º\" sin punto, con la º como superíndice", () => {
    render(wrap(<TeamCard payload={{ ...structuredClone(FIXTURES.team_card), position: 3 }} demoData />));
    expect(screen.getByTestId("tc-pos")).toHaveTextContent("3º");
    expect(screen.getByTestId("tc-pos").querySelector("sup")).not.toBeNull();
    expect(screen.getByTestId("tc-pos")).not.toHaveTextContent("3.º");
  });

  it("sin forma ni posición no revienta", () => {
    const p = { ...structuredClone(FIXTURES.team_card), form: [], position: null, points: null };
    render(wrap(<TeamCard payload={p} demoData />));
    expect(screen.queryByTestId("tc-pos")).toBeNull();
  });
});

describe("Situation", () => {
  it("tercio inferior: título en una línea sin píldora, protagonista, otro jugador, 2 cifras y banda de hoy; sin minicampo en un penalti", () => {
    const { container } = render(wrap(<Situation payload={FIXTURES.situation} demoData />));
    expect(container.querySelector(".panel--lower")).not.toBeNull();
    expect(screen.getByTestId("si-title")).toHaveTextContent("Penalti provocado");
    expect(screen.queryByTestId("si-role")).toBeNull();
    expect(screen.getByTestId("si-subject")).toHaveTextContent("Lamine Yamal");
    expect(screen.getByTestId("si-other")).toHaveTextContent("Juma Bah");
    expect(screen.getAllByTestId("si-fig")).toHaveLength(2);
    expect(screen.getAllByTestId("si-fig")[1]).toHaveTextContent("2de2"); // "2 · 2" ambiguo → "2 DE 2"
    expect(screen.getByTestId("si-match")).toHaveTextContent(/4\s*faltas recibidas/);
    expect(screen.getByTestId("si-match")).not.toHaveTextContent(/hoy/i);
    expect(container.querySelector('[data-testid="pitch"]')).toBeNull();
  });

  it("una falta con tiros lleva campo completo con el punto a 24 px", () => {
    const p = { ...structuredClone(FIXTURES.situation), event_type: "falta", title: "Falta", role_label: null };
    const { container } = render(wrap(<Situation payload={p} demoData />));
    expect(container.querySelector('[data-testid="pitch"]')).not.toBeNull();
    const shots = container.querySelectorAll("circle[data-shot]");
    expect(shots).toHaveLength(1);
    expect(shots[0]!.getAttribute("r")).toBe("12");
  });

  it("sin sujeto sólo el título", () => {
    const p = { ...structuredClone(FIXTURES.situation), shots: [], other: null, subject: null, subject_type: null };
    const { container } = render(wrap(<Situation payload={p} demoData />));
    expect(container.querySelector('[data-testid="pitch"]')).toBeNull();
    expect(screen.queryByTestId("si-subject")).toBeNull();
    expect(screen.getByTestId("si-title")).toBeInTheDocument();
  });
});

describe("Timeline", () => {
  const ev = (id: string, minute: number, major = false): TimelineItem => ({
    id, minute, t_audio: minute * 60, type: "gol", label: `Gol · ${id}`, major, status: "auto", players: [],
  });

  it("ANTENA (por defecto): sin descartados ni detalle menor, y NINGUNA marca de moderación", () => {
    const { container } = render(wrap(<Timeline payload={FIXTURES.timeline} demoData />));
    const evs = screen.getAllByTestId("tl-event");
    // 11 eventos en el fixture: salen solo goles, tarjetas y cambios CONFIRMADOS (approved/edited): gol×3, amarilla y cambio.
    // Quedan fuera el descartado (regate), el penalti (sale como el gol que provoca), los menores y la amarilla sin confirmar ("auto").
    expect(evs).toHaveLength(5);
    expect(new Set(evs.map((e) => e.getAttribute("data-type")))).toEqual(new Set(["gol", "amarilla", "cambio"]));
    expect(container.querySelector(".tl__sr")!.textContent).not.toContain("65'"); // la amarilla "auto" de Cubarsí
    expect(container.querySelectorAll("[data-status]")).toHaveLength(0); // ni atributo de estado
    expect(container.querySelector(".tl__ev--discarded, .tl__ev--approved, .tl__ev--edited, .tl__ev--auto")).toBeNull();
    // ni ✓ verde, ni lápiz, ni tachado rojo, ni aro discontinuo
    expect(container.querySelector('svg [stroke-dasharray]')).toBeNull();
    expect(container.querySelector('path[d^="M-4.5 0"]')).toBeNull(); // ✓
    expect(container.querySelector('path[d^="M-3.5 3.5"]')).toBeNull(); // lápiz
    expect(container.querySelector('path[d="M6 42 L42 6"]')).toBeNull(); // tachado
    expect(container.querySelector("[style*='line-through'], .tl__ev--discarded")).toBeNull();
    // las tarjetas van sin disco: un rectángulo sólido
    const yellow = container.querySelector('[data-icon="amarilla"]')!;
    expect(yellow.querySelector("circle")).toBeNull();
    expect(yellow.querySelector("rect")).not.toBeNull();
    expect(screen.getByTestId("tl-halftime")).toBeInTheDocument();
    expect(screen.getByTestId("tl-progress")).toBeInTheDocument();
    // el marcador sale del propio listado: 2 – 1 a los 67'
    expect(screen.getByTestId("tl-score")).toHaveTextContent("2 – 1");
    expect(screen.getByTestId("tl-score")).toHaveTextContent("67'");
  });

  it("antena: un evento descartado no se pinta nunca, ni en el texto accesible", () => {
    const p = structuredClone(FIXTURES.timeline);
    p.items.push({ ...ev("x", 70, true), team: p.home, status: "discarded" });
    const { container } = render(wrap(<Timeline payload={p} demoData />));
    expect(screen.getAllByTestId("tl-event")).toHaveLength(5);
    expect(container.querySelector(".tl__sr")!.textContent).not.toContain("70'");
    expect(screen.getByTestId("tl-score")).toHaveTextContent("2 – 1"); // el gol descartado no cuenta
  });

  it("antena: un evento sin confirmar (auto o sin estado) no se pinta; con editorial sí, con su estado", () => {
    const p = structuredClone(FIXTURES.timeline);
    p.items.push({ ...ev("g", 70, true), team: p.away, status: "auto" }); // gol sin confirmar
    p.items.push({ id: "n", minute: 71, t_audio: 1, type: "gol", label: "Gol", team: p.away }); // sin estado = sin confirmar
    const { container, rerender } = render(wrap(<Timeline payload={p} demoData />));
    expect(screen.getAllByTestId("tl-event")).toHaveLength(5);
    expect(screen.getByTestId("tl-score")).toHaveTextContent("2 – 1"); // el gol "auto" no cuenta en el marcador de antena
    rerender(wrap(<Timeline payload={p} demoData editorial />));
    expect(container.querySelectorAll('[data-testid="tl-event"]')).toHaveLength(13);
  });

  it("las cifras del gutter se estilan por CLASE (`.tl__score`, `.tl__team`), no por etiqueta: así nada pisa el marcador de 56 px", () => {
    const { container } = render(wrap(<Timeline payload={FIXTURES.timeline} demoData />));
    expect(container.querySelector(".tl__gutter--mid .tl__score")).not.toBeNull();
    const names = [...container.querySelectorAll(".tl__gutter--top b, .tl__gutter--bottom b")];
    expect(names).toHaveLength(2);
    for (const n of names) expect(n.classList.contains("tl__team")).toBe(true);
  });

  it("editorial: los 11 eventos con su estado (descartado, ✓, lápiz, aro discontinuo)", () => {
    const { container } = render(wrap(<Timeline payload={FIXTURES.timeline} demoData editorial />));
    const evs = screen.getAllByTestId("tl-event");
    expect(evs).toHaveLength(11);
    expect(evs.filter((e) => e.getAttribute("data-status") === "discarded")).toHaveLength(1);
    expect(evs.filter((e) => e.getAttribute("data-status") === "approved").length).toBeGreaterThanOrEqual(3);
    expect(evs.filter((e) => e.getAttribute("data-status") === "auto").length).toBeGreaterThanOrEqual(1);
    expect(evs.filter((e) => e.getAttribute("data-status") === "edited")).toHaveLength(1);
    expect(evs.filter((e) => e.getAttribute("data-major") === "true").length).toBe(4);
    expect(new Set(evs.map((e) => e.getAttribute("data-type")))).toEqual(
      new Set(["gol", "amarilla", "corner", "penalti", "cambio", "regate", "parada", "tiro"]),
    );
    expect(container.querySelectorAll("[data-icon]")).toHaveLength(11);
    expect(container.querySelector('svg [stroke-dasharray]')).not.toBeNull(); // aro de "sin confirmar"
    expect(container.querySelector('path[d^="M-4.5 0"]')).not.toBeNull(); // ✓ de aprobado
    expect(container.querySelector('path[d="M6 42 L42 6"]')).not.toBeNull(); // tachado del descartado
    expect(container.querySelector(".tl__ev--discarded")).not.toBeNull();
  });

  it("GraphicView pasa editorial al grafismo (por defecto, antena)", () => {
    const g = { payload: FIXTURES.timeline, demo_data: true };
    const { container, rerender } = render(wrap(<GraphicView graphic={g} />));
    expect(screen.getAllByTestId("tl-event")).toHaveLength(5);
    rerender(wrap(<GraphicView graphic={g} editorial />));
    expect(container.querySelectorAll('[data-testid="tl-event"]')).toHaveLength(11);
  });

  it("layoutSide: sin solapes, orden temporal, dentro del eje y poco desplazamiento", () => {
    const items = [ev("a", 52, true), ev("b", 53, true), ev("c", 54), ev("d", 55), ev("e", 3), ev("f", 90)];
    const placed = layoutSide(items, AXIS_W / 90);
    expect(placed.map((p) => p.minute)).toEqual([3, 52, 53, 54, 55, 90]);
    // los iconos se apartan poco de su minuto (las etiquetas no los empujan): menos de ~2 iconos
    for (const p of placed) expect(Math.abs(p.x - p.trueX)).toBeLessThan(140);
    for (let i = 1; i < placed.length; i++) {
      const a = placed[i - 1]!;
      const b = placed[i]!;
      expect(b.x - b.w / 2).toBeGreaterThanOrEqual(a.x + a.w / 2 + 9.99);
    }
    for (const p of placed) {
      expect(p.x - p.w / 2).toBeGreaterThanOrEqual(-0.01);
      expect(p.x + p.w / 2).toBeLessThanOrEqual(AXIS_W + 0.01);
    }
    // un evento aislado queda exactamente en su minuto
    expect(placed[0]!.x).toBeCloseTo(placed[0]!.trueX, 5);
  });

  it("eventKind normaliza tipos libres", () => {
    expect(eventKind("córner")).toBe("corner");
    expect(eventKind("Fuera de juego")).toBe("fuera_de_juego");
    expect(eventKind("algo raro")).toBe("otro");
  });

  it("las etiquetas que chocan suben a una segunda fila y ninguna se sale del eje", () => {
    const placed = layoutSide([ev("a", 52, true), ev("b", 53, true), ev("c", 55, true)], AXIS_W / 90, AXIS_W, true);
    expect(placed.some((p) => p.tier === 1)).toBe(true);
    for (const p of placed) {
      const lw = p.text!.length * 13;
      expect(p.x + p.shift - lw / 2).toBeGreaterThanOrEqual(-0.01);
      expect(p.x + p.shift + lw / 2).toBeLessThanOrEqual(AXIS_W + 0.01);
    }
  });

  it("ignora los eventos sin minuto y admite tiempo añadido (>90)", () => {
    const p = structuredClone(FIXTURES.timeline);
    p.items.push({ id: "x", minute: null, t_audio: 1, type: "gol", label: "?", team: p.home });
    p.items.push({ ...ev("late", 94), team: p.away, status: "approved" });
    p.minute = 95;
    render(wrap(<Timeline payload={p} demoData />));
    expect(screen.getAllByTestId("tl-event")).toHaveLength(6);
  });
});

describe("Scorebug", () => {
  it("siglas, goles, minuto y periodo", () => {
    render(wrap(<Scorebug payload={FIXTURES.scorebug} demoData />));
    expect(screen.getByTestId("sb-home")).toHaveTextContent("BAR");
    expect(screen.getByTestId("sb-away")).toHaveTextContent("VLL");
    expect(screen.getAllByTestId("sb-goals").map((g) => g.textContent)).toEqual(["2", "1"]);
    expect(screen.getByTestId("sb-time")).toHaveTextContent("67'");
    expect(screen.getByTestId("sb-time")).not.toHaveTextContent("2.ª parte"); // el reloj ya lo dice
  });

  it("con el reloj parado muestra el periodo, y la banda de demostración va pegada al marcador", () => {
    const { container } = render(wrap(<Scorebug payload={{ ...FIXTURES.scorebug, period: 3, minute: 90 }} demoData />));
    expect(screen.getByTestId("sb-time")).toHaveTextContent("Final");
    expect(container.querySelector(".sb-wrap > .demo-badge--band")).not.toBeNull();
  });

  it("minuteText: tiempo añadido y reloj parado", () => {
    expect(minuteText(45, 2, 1)).toBe("45+2'");
    expect(minuteText(90, null, 3)).toBeNull();
    expect(minuteText(null, null, 1)).toBeNull();
  });
});

describe("galería a tamaño real", () => {
  it("?size=1920 pinta el lienzo a 1920 px sin escalar", () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/gallery?only=scorebug&size=1920&bare=1"]}>
        <Gallery />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("stage-fixed")).toHaveStyle({ width: "1920px" });
    const inner = container.querySelector('[data-testid="stage"] > div') as HTMLElement;
    expect(inner.style.transform).toBe("scale(1)");
  });

  it("sin ?size usa la rejilla escalada", () => {
    render(
      <MemoryRouter initialEntries={["/gallery?only=scorebug"]}>
        <Gallery />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("stage-fixed")).toBeNull();
  });
});

describe("H2H · casos límite", () => {
  it("un tramo a 0 no se pinta ni ocupa columna en la barra, y su cifra queda al 60 %", () => {
    const p = { ...FIXTURES.h2h, played: 8, a_wins: 7, draws: 0, b_wins: 1 };
    const { container } = render(wrap(<H2H payload={p} demoData />));
    expect((screen.getByTestId("h2h-bar") as HTMLElement).style.gridTemplateColumns).toBe("7fr 1fr");
    expect([...container.querySelectorAll("[data-seg]")].map((s) => s.getAttribute("data-seg"))).toEqual(["a", "b"]);
    expect(container.querySelector(".h2h__fig--d")!.className).toMatch(/is-zero/);
  });
  it("sin partidos previos: pista neutra con aviso, sin NaN", () => {
    const p = { ...FIXTURES.h2h, played: 0, a_wins: 0, draws: 0, b_wins: 0, a_goals: 0, b_goals: 0, last: [] };
    const { container } = render(wrap(<H2H payload={p} demoData variant="full" />));
    expect(container.querySelectorAll("[data-seg]")).toHaveLength(0);
    expect(screen.getByTestId("h2h-bar")).toHaveTextContent(/Sin enfrentamientos previos/);
    expect(container.innerHTML).not.toMatch(/NaN|Infinity/);
  });
});

