import { describe, expect, it } from "vitest";
import { accentOn, contrast, GLASS_REF, inkOn, pairAccents } from "./color";
import { BARCELONA, LEAGUE_TEAMS, VALLADOLID } from "../fixtures";

describe("color", () => {
  it("contraste WCAG: negro/blanco = 21", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 0);
  });

  it("accentOn aclara los colores oscuros hasta contraste ≥ 3 sobre el cristal sin forzar la saturación y respeta los claros", () => {
    expect(contrast(accentOn("#5E2D91"), GLASS_REF)).toBeGreaterThanOrEqual(3);
    expect(accentOn("#FFD23F")).toBe("#ffd23f");
  });

  it("todos los colores primarios de los 20 equipos quedan con contraste AA como acento", () => {
    for (const t of Object.values(LEAGUE_TEAMS)) expect(contrast(accentOn(t.colors.primary!), GLASS_REF)).toBeGreaterThanOrEqual(3);
  });

  it("inkOn escoge el texto más legible", () => {
    expect(inkOn("#ffffff")).toBe("#06090f");
    expect(inkOn("#5E2D91")).toBe("#ffffff");
  });

  it("pairAccents separa a dos jugadores del mismo club usando el secundario", () => {
    const [a, b] = pairAccents(BARCELONA.colors, BARCELONA.colors);
    expect(a).not.toBe(b);
    expect(contrast(b, GLASS_REF)).toBeGreaterThanOrEqual(3);
    const [c, d] = pairAccents(BARCELONA.colors, VALLADOLID.colors);
    expect(c).not.toBe(d);
  });
});
