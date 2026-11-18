import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Shot } from "../contracts";
import { ArrowsLayer, arrowGeometry, arrowWidth } from "./ArrowsLayer";
import { AttackArrow } from "./AttackArrow";
import { HeatLayer, ThirdsLines, thirdsShare } from "./HeatLayer";
import { NodesLayer } from "./NodesLayer";
import { Pitch } from "./Pitch";
import { ShotsLayer, shotRadiusM } from "./ShotsLayer";
import { usePitch, type PitchCtx } from "./context";

// 1110 px de ancho y margen 30: 10 px por metro, origen de datos abajo-izquierda.
const W = { width: 1110, padding: 30 };

const shot = (x: number, y: number, xg: number, outcome: Shot["outcome"] = "saved"): Shot => ({
  x, y, xg, outcome, minute: 10, player: "p", player_name: "P",
});

describe("escalas del campo (contexto)", () => {
  it("origen abajo-izquierda: (0,0) → esquina inferior izquierda, (105,68) → superior derecha", () => {
    let ctx: PitchCtx | undefined;
    const Probe = () => {
      ctx = usePitch();
      return null;
    };
    render(<Pitch {...W}><Probe /></Pitch>);
    expect(ctx!.x(0)).toBe(30);
    expect(ctx!.y(0)).toBe(710);
    expect(ctx!.x(105)).toBe(1080);
    expect(ctx!.y(68)).toBe(30);
    expect(ctx!.k).toBe(10);
  });

  it("las capas fuera de <Pitch> fallan con un mensaje claro", () => {
    const orig = console.error;
    console.error = () => {}; // React registra el error del límite antes de relanzarlo
    const mute = (e: ErrorEvent) => e.preventDefault(); // y jsdom lo reenvía como "uncaught"
    window.addEventListener("error", mute);
    try {
      expect(() => render(<ShotsLayer shots={[]} />)).toThrow(/dentro de <Pitch>/);
    } finally {
      window.removeEventListener("error", mute);
      console.error = orig;
    }
  });
});

describe("ShotsLayer", () => {
  it("coloca un tiro en (x,y) → píxeles con y invertida", () => {
    const { container } = render(
      <Pitch {...W}>
        <ShotsLayer shots={[shot(94, 34, 0.1), shot(0, 0, 0.1), shot(105, 68, 0.1), shot(88.5, 10, 0.2)]} legend={false} />
      </Pitch>,
    );
    const cs = [...container.querySelectorAll("[data-shot]")].map((c) => [Number(c.getAttribute("cx")), Number(c.getAttribute("cy"))]);
    expect(cs).toContainEqual([970, 370]); // punto de penalti derecho
    expect(cs).toContainEqual([30, 710]); // esquina inferior izquierda
    expect(cs).toContainEqual([1080, 30]); // esquina superior derecha
    expect(cs).toContainEqual([915, 610]); // y=10 m está CERCA del borde inferior
  });

  it("el radio crece con el xG y los goles se pintan encima y rellenos", () => {
    const { container } = render(
      <Pitch {...W}>
        <ShotsLayer shots={[shot(90, 30, 0.76, "goal"), shot(80, 30, 0.04), shot(85, 30, 0.4)]} legend={false} />
      </Pitch>,
    );
    const all = [...container.querySelectorAll("circle[data-shot]")];
    const r = (el: Element) => Number(el.getAttribute("r"));
    const small = all.find((c) => c.getAttribute("data-xg") === "0.04")!;
    const mid = all.find((c) => c.getAttribute("data-xg") === "0.4")!;
    const goal = all.find((c) => c.getAttribute("data-shot") === "goal")!;
    expect(r(small)).toBeGreaterThanOrEqual(8); // radio mínimo
    expect(r(small)).toBeLessThan(r(mid));
    expect(r(goal)).toBeLessThanOrEqual(16); // todos los tiros se limitan a 16 px para no pisarse
    expect(all[all.length - 1]).toBe(goal); // último = encima
    expect(goal.getAttribute("fill")).toContain("var(--club-fill"); // color oficial del club, no el acento aclarado
    expect(goal.getAttribute("stroke")).toBe("#ffffff");
  });

  it("dibuja la leyenda si hay banda inferior", () => {
    const { container } = render(<Pitch {...W} bottomBand={56}><ShotsLayer shots={[]} /></Pitch>);
    expect(container.querySelector('[data-layer="shots-legend"]')).not.toBeNull();
  });
});

describe("ArrowsLayer", () => {
  it("la punta de la flecha termina en el punto de destino (con holgura)", () => {
    const g = arrowGeometry({ x: 0, y: 0 }, { x: 100, y: 0 }, 4, 0, 10);
    expect(g.head.startsWith("90,0 ")).toBe(true);
  });

  it("a→b y b→a se curvan hacia lados opuestos", () => {
    const ab = arrowGeometry({ x: 0, y: 0 }, { x: 100, y: 0 }, 4).path;
    const ba = arrowGeometry({ x: 100, y: 0 }, { x: 0, y: 0 }, 4).path;
    const cy = (p: string) => Number(p.match(/Q [\d.-]+ ([\d.-]+)/)![1]);
    expect(Math.sign(cy(ab))).toBe(-Math.sign(cy(ba)));
  });

  it("el grosor crece con el recuento", () => {
    const { container } = render(
      <Pitch {...W}>
        <ArrowsLayer
          arrows={[
            { x: 10, y: 10, end_x: 40, end_y: 10, count: 1 },
            { x: 10, y: 30, end_x: 40, end_y: 30, count: 25 },
          ]}
        />
      </Pitch>,
    );
    const w = [...container.querySelectorAll("[data-arrow]")].map((g) => Number(g.querySelectorAll("path")[1]!.getAttribute("stroke-width")));
    expect(w[1]).toBeGreaterThan(w[0]!);
    expect(w[0]).toBeGreaterThanOrEqual(4);
  });

  it("arrowWidth: lineal desde el umbral (10 → 4 px, máximo → 18 px) y distinguible en la leyenda", () => {
    expect(arrowWidth(10, 26, 10)).toBe(4);
    expect(arrowWidth(26, 26, 10)).toBe(18);
    expect(arrowWidth(18, 26, 10)).toBeCloseTo(11, 5);
    expect(arrowWidth(3, 26, 10)).toBe(4); // por debajo del umbral se queda en el mínimo
  });

  it("los pares de ida y vuelta se separan con un desplazamiento perpendicular", () => {
    const flat = arrowGeometry({ x: 0, y: 0 }, { x: 100, y: 0 }, 4, 0, 0, 0, 0);
    const moved = arrowGeometry({ x: 0, y: 0 }, { x: 100, y: 0 }, 4, 0, 0, 0, 7);
    expect(flat.path.startsWith("M 0 0 ")).toBe(true);
    expect(moved.path.startsWith("M 0 7 ")).toBe(true);
  });

  it("paleta única: pase blanco al 45 %, pase clave blanco pleno, asistencia dorada; la destacada, color del club con contorno blanco", () => {
    const { container } = render(
      <Pitch {...W}>
        <ArrowsLayer
          highlightColor="#a50044"
          arrows={[
            { x: 10, y: 10, end_x: 40, end_y: 10 },
            { x: 10, y: 30, end_x: 40, end_y: 30, kind: "key_pass" },
            { x: 10, y: 40, end_x: 40, end_y: 40, kind: "assist" },
            { x: 10, y: 50, end_x: 40, end_y: 50, highlight: true, count: 20 },
          ]}
        />
      </Pitch>,
    );
    const g = (k: string) => container.querySelector(k)!;
    const op = (el: Element) => el.getAttribute("opacity");
    expect(op(g('[data-arrow="pass"]'))).toBe("0.45");
    expect(op(g('[data-arrow="key_pass"]'))).toBe("1");
    expect(g('[data-arrow="assist"] path:last-of-type').getAttribute("stroke")).toBe("#ffd23f");
    expect(g('[data-arrow="assist"] path:last-of-type').getAttribute("stroke-width")).toBe("5");
    const hl = g('[data-highlight="true"]');
    expect(hl.querySelectorAll("path")[0]!.getAttribute("stroke")).toBe("#ffffff"); // contorno blanco
    expect(hl.querySelectorAll("path")[1]!.getAttribute("stroke")).toBe("#a50044");
    expect(container.innerHTML).not.toMatch(/7cf0d0/i);
  });

  it("convierte las coordenadas del dato a píxeles (origen abajo-izquierda)", () => {
    const { container } = render(
      <Pitch {...W}><ArrowsLayer arrows={[{ x: 0, y: 0, end_x: 50, end_y: 0, count: 1 }]} /></Pitch>,
    );
    const d = container.querySelector("[data-arrow] path")!.getAttribute("d")!;
    expect(d.startsWith("M 30 710 ")).toBe(true);
  });
});

describe("NodesLayer", () => {
  const node = (id: string, x: number, y: number, size: number) => ({
    id, x, y, size, label: id, number: 7, fill: "#a50044", textColor: "#fff",
  });

  it("posición en píxeles y radio ∝ √pases", () => {
    const { container } = render(
      <Pitch {...W}><NodesLayer nodes={[node("a", 52.5, 34, 20), node("b", 10, 60, 90)]} /></Pitch>,
    );
    const a = container.querySelector('[data-node="a"]')!;
    const b = container.querySelector('[data-node="b"]')!;
    expect(a.querySelector("circle")!.getAttribute("cx")).toBe("555");
    expect(a.querySelector("circle")!.getAttribute("cy")).toBe("370");
    expect(Number(b.getAttribute("data-r"))).toBeGreaterThan(Number(a.getAttribute("data-r")));
    expect(b.textContent).toContain("7");
  });
});

describe("HeatLayer", () => {
  function mean(d: string) {
    const nums = [...d.matchAll(/[ML]([\d.-]+) ([\d.-]+)/g)].map((m) => [Number(m[1]), Number(m[2])] as const);
    return [nums.reduce((s, p) => s + p[0], 0) / nums.length, nums.reduce((s, p) => s + p[1], 0) / nums.length];
  }

  it("fila 0 de la rejilla = y=0 = parte INFERIOR del campo", () => {
    const cols = 10;
    const rows = 6;
    const grid = new Array(cols * rows).fill(0);
    grid[0] = 1; // esquina inferior izquierda
    grid[1] = 1;
    grid[cols] = 1;
    const { container } = render(<Pitch {...W}><HeatLayer grid={grid} cols={cols} rows={rows} /></Pitch>);
    const paths = [...container.querySelectorAll("[data-heat-level]")];
    expect(paths.length).toBeGreaterThan(2);
    const hottest = paths[paths.length - 1]!;
    const [mx, my] = mean(hottest.getAttribute("d")!);
    expect(mx!).toBeLessThan(30 + 525); // mitad izquierda
    expect(my!).toBeGreaterThan(30 + 340); // mitad inferior
  });

  it("una rejilla uniforme no rompe", () => {
    const { container } = render(<Pitch {...W}><HeatLayer grid={new Array(12).fill(0.5)} cols={4} rows={3} /></Pitch>);
    expect(container.querySelector('[data-layer="heat"]')).not.toBeNull();
  });
});

describe("Pitch con recorte (view)", () => {
  it("medio campo atacante: x=52,5 m queda en el borde izquierdo y la portería (105) deja margen a la derecha", () => {
    let ctx: PitchCtx | undefined;
    const Probe = () => {
      ctx = usePitch();
      return null;
    };
    render(<Pitch width={636} padding={24} view={{ x0: 52.5 }}><Probe /></Pitch>);
    expect(ctx!.x(52.5)).toBeCloseTo(0);
    expect(ctx!.x(105)).toBeCloseTo(612);
    expect(ctx!.k).toBeCloseTo(612 / 52.5);
    expect(ctx!.y(68)).toBe(24); // el borde superior sí tiene margen
    expect(ctx!.y(0)).toBeCloseTo(24 + 68 * ctx!.k);
  });

  it("sin view se comporta como antes", () => {
    let ctx: PitchCtx | undefined;
    const Probe = () => {
      ctx = usePitch();
      return null;
    };
    render(<Pitch {...W}><Probe /></Pitch>);
    expect(ctx!.k).toBe(10);
    expect(ctx!.height).toBe(740);
  });
});

describe("radio de los tiros", () => {
  it("el ÁREA del círculo es proporcional al xG (salvo el mínimo visible)", () => {
    const area = (xg: number) => shotRadiusM(xg) ** 2;
    expect(area(0.8) / area(0.2)).toBeCloseTo(4, 1);
    expect(area(0.4) / area(0.1)).toBeCloseTo(4, 1);
    expect(shotRadiusM(0.001)).toBeGreaterThanOrEqual(0.7);
  });
});

describe("plantilla común de campo", () => {
  it("topBand desplaza el campo hacia abajo y el sentido de ataque se dibuja en esa banda, fuera del césped", () => {
    let ctx: PitchCtx | undefined;
    const Probe = () => {
      ctx = usePitch();
      return null;
    };
    const { container } = render(
      <Pitch {...W} topBand={60}>
        <Probe />
        <AttackArrow />
      </Pitch>,
    );
    expect(ctx!.y(68)).toBe(60 + 30); // banda + margen
    expect(ctx!.height).toBe(740 + 60);
    const g = container.querySelector('[data-layer="attack-arrow"]')!;
    const text = g.querySelector("text")!;
    expect(Number(text.getAttribute("y"))).toBe(30); // centro de la banda, por encima del césped (y ≥ 90)
    expect(text.textContent).toBe("ATAQUE"); // un único rótulo en los cuatro grafismos de campo
  });

  it("thirdsShare reparte la rejilla en tercios que suman 100 y ThirdsLines dibuja dos líneas", () => {
    const cols = 6;
    const rows = 2;
    const grid = [1, 1, 1, 1, 6, 6, 1, 1, 1, 1, 6, 6]; // todo el peso en el último tercio
    const t = thirdsShare(grid, cols, rows);
    expect(t.reduce((a, b) => a + b, 0)).toBe(100);
    expect(t[2]).toBeGreaterThan(t[0]);
    expect(thirdsShare([0, 0, 0], 3, 1)).toEqual([0, 0, 0]);
    const { container } = render(<Pitch {...W}><ThirdsLines /></Pitch>);
    expect(container.querySelectorAll('[data-layer="thirds"] line')).toHaveLength(2);
  });
});
