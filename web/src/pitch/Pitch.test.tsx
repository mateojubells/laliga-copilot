import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Pitch } from "./Pitch";
import { PITCH, penaltyArcHalfChord } from "./geometry";

// Con width=1110 y padding=30 el campo mide 1050×680 px: exactamente 10 px por metro.
const K = 10;
const PAD = 30;
const px = (m: number) => PAD + m * K;
const py = (m: number) => PAD + (68 - m) * K; // origen abajo-izquierda

function setup() {
  const { container } = render(<Pitch width={1110} padding={30} />);
  const q = (name: string) => container.querySelector(`[data-line="${name}"]`)!;
  const n = (el: Element, a: string) => Number(el.getAttribute(a));
  return { container, q, n };
}

describe("Pitch: líneas reglamentarias", () => {
  it("el viewBox es 105×68 m a 10 px/m más el margen", () => {
    const { container } = setup();
    expect(container.querySelector("svg")!.getAttribute("viewBox")).toBe("0 0 1110 740");
    expect(container.querySelector("svg")!.dataset.k).toBe("10");
  });

  it("contorno 105×68", () => {
    const { q, n } = setup();
    const o = q("outline");
    expect([n(o, "x"), n(o, "y"), n(o, "width"), n(o, "height")]).toEqual([30, 30, 1050, 680]);
  });

  it("línea de medio campo y círculo central de 9,15 m", () => {
    const { q, n } = setup();
    expect(n(q("halfway"), "x1")).toBeCloseTo(px(52.5));
    const c = q("center-circle");
    expect(n(c, "cx")).toBeCloseTo(px(52.5));
    expect(n(c, "cy")).toBeCloseTo(py(34));
    expect(n(c, "r")).toBeCloseTo(91.5);
  });

  it("punto de penalti a 11 m de cada línea de gol, centrado", () => {
    const { q, n } = setup();
    const l = q("penalty-spot-left");
    const r = q("penalty-spot-right");
    expect(n(l, "cx")).toBeCloseTo(px(11));
    expect(n(l, "cy")).toBeCloseTo(py(34));
    expect(n(r, "cx")).toBeCloseTo(px(105 - 11));
    expect(n(r, "cy")).toBeCloseTo(py(34));
  });

  it("área grande de 40,32 × 16,5 m centrada", () => {
    const { q, n } = setup();
    const a = q("penalty-area-left");
    expect(n(a, "width")).toBeCloseTo(16.5 * K);
    expect(n(a, "height")).toBeCloseTo(40.32 * K);
    expect(n(a, "x")).toBeCloseTo(px(0));
    expect(n(a, "y")).toBeCloseTo(py(34 + 20.16));
    const b = q("penalty-area-right");
    expect(n(b, "x")).toBeCloseTo(px(105 - 16.5));
    expect(n(b, "width")).toBeCloseTo(16.5 * K);
  });

  it("área pequeña de 18,32 × 5,5 m", () => {
    const { q, n } = setup();
    const a = q("goal-area-left");
    expect(n(a, "width")).toBeCloseTo(5.5 * K);
    expect(n(a, "height")).toBeCloseTo(18.32 * K);
    expect(n(a, "y")).toBeCloseTo(py(34 + 9.16));
  });

  it("portería de 7,32 m dibujada por detrás de la línea de fondo", () => {
    const { q, n } = setup();
    const g = q("goal-left");
    expect(n(g, "height")).toBeCloseTo(7.32 * K);
    expect(n(g, "x") + n(g, "width")).toBeCloseTo(px(0));
    expect(n(g, "width")).toBeCloseTo(2.44 * K);
    const h = q("goal-right");
    expect(n(h, "x")).toBeCloseTo(px(105));
  });

  it("semicírculo del área: radio 9,15 m desde el punto de penalti, fuera del área", () => {
    const { q } = setup();
    for (const side of ["left", "right"] as const) {
      const d = q(`penalty-arc-${side}`).getAttribute("d")!;
      const m = d.match(/M ([\d.-]+) ([\d.-]+) A ([\d.-]+) ([\d.-]+) 0 0 (\d) ([\d.-]+) ([\d.-]+)/)!;
      const [sx, sy, r, , sweep, ex, ey] = m.slice(1).map(Number);
      const spotX = side === "left" ? px(11) : px(94);
      const spotY = py(34);
      expect(r).toBeCloseTo(91.5);
      expect(Math.hypot(sx! - spotX, sy! - spotY)).toBeCloseTo(91.5, 1);
      expect(Math.hypot(ex! - spotX, ey! - spotY)).toBeCloseTo(91.5, 1);
      // los extremos están sobre la línea del área (x = 16,5 m desde el fondo)
      const lineX = side === "left" ? px(16.5) : px(105 - 16.5);
      expect(sx).toBeCloseTo(lineX);
      expect(ex).toBeCloseTo(lineX);
      expect(Math.abs(sy! - ey!)).toBeCloseTo(2 * penaltyArcHalfChord() * K, 1);
      // sentido: el arco abomba hacia el centro del campo (izq: horario; der: antihorario)
      expect(sweep).toBe(side === "left" ? 1 : 0);
    }
  });

  it("cuatro arcos de esquina de 1 m", () => {
    const { container } = setup();
    expect(container.querySelectorAll('[data-line="corner-arc"]').length).toBe(4);
  });

  it("las medidas reglamentarias constan en geometry", () => {
    expect(PITCH.penaltyArea).toEqual({ depth: 16.5, width: 40.32 });
    expect(PITCH.penaltySpot).toBe(11);
  });

  it("franjas de césped alternas", () => {
    const { container } = setup();
    expect(container.querySelectorAll("[data-stripe]").length).toBe(7);
  });
});
