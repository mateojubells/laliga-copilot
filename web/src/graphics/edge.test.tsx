import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { GRAPHIC_KINDS } from "../contracts";
import { ImageSourceProvider } from "../design";
import { EDGE_FIXTURES, FIXTURES } from "../fixtures";
import { fitView } from "../pitch";
import { GraphicView } from "./GraphicFrame";
import { shotHeadline } from "./ShotMap";
import { surname } from "./shared";

const wrap = (n: React.ReactNode) => (
  <MemoryRouter><ImageSourceProvider mode="generated">{n}</ImageSourceProvider></MemoryRouter>
);

describe("casos límite", () => {
  for (const kind of GRAPHIC_KINDS) {
    it(`${kind}: se pinta sin NaN, Infinity ni undefined`, () => {
      for (const editorial of [false, true]) {
        const { container, unmount } = render(wrap(<GraphicView graphic={{ payload: EDGE_FIXTURES[kind], demo_data: true }} editorial={editorial} />));
        expect(container.innerHTML).not.toMatch(/NaN|Infinity|undefined/);
        unmount();
      }
    });
  }

  it("escala del campo: ninguna marca por debajo de 9 px/m en shot_map ni connection (normal y límite)", () => {
    for (const set of [FIXTURES, EDGE_FIXTURES]) {
      for (const kind of ["shot_map", "connection"] as const) {
        const { getByTestId, unmount } = render(wrap(<GraphicView graphic={{ payload: set[kind], demo_data: true }} />));
        expect(Number(getByTestId("pitch").getAttribute("data-k"))).toBeGreaterThanOrEqual(9);
        unmount();
      }
    }
  });

  it("fitView: recorta a la zona, respeta la escala mínima y no se dispara con puntos juntos", () => {
    const fb = { x0: 0, x1: 60, y0: 0, y1: 40 };
    const far = fitView([[40, 30], [100, 30]], { width: 400, padding: 24, minK: 9, anchor: "right", fallback: fb });
    expect(376 / (far.x1 - far.x0)).toBeGreaterThanOrEqual(9 - 1e-6);
    expect(far.x1).toBe(105);
    expect(376 / (far.x1 - far.x0)).toBeGreaterThanOrEqual(9 - 1e-6);
    const close = fitView([[50, 30], [51, 30]], { width: 560, padding: 24, maxK: 13, fallback: fb });
    expect(560 / (close.x1 - close.x0)).toBeLessThanOrEqual(13 + 1e-6);
    expect(fitView([], { width: 400, padding: 24, minK: 1, maxK: 99, fallback: fb })).toEqual(fb);
  });

  it("titular de tiros y apellidos con partículas", () => {
    expect(shotHeadline(8, 5.2, 26)).toBe("8 goles con 5,2 de xG: 2,8 por encima de lo esperado");
    expect(shotHeadline(0, 0, 0)).toBeNull();
    expect(surname({ known_as: "Marc-André ter Stegen" })).toBe("ter Stegen");
    expect(surname({ known_as: "Íñigo Martínez Berridi" })).toBe("Berridi");
    expect(surname({ known_as: "De Jong" })).toBe("De Jong");
  });
});
