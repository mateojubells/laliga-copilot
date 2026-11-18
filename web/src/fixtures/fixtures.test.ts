import { describe, expect, it } from "vitest";
import { GRAPHIC_KINDS, type GraphicKind } from "../contracts";
import { ALL_FIXTURES, FIXTURES, standingsFull } from "./index";

// El tipado de FIXTURES ({ [K in GraphicKind]: PayloadOf<K> }) ya obliga en `tsc` a que cada fixture cumpla su
// tipo del contrato y a que estén los 12; estas pruebas comprueban además la coherencia de los datos.
describe("fixtures", () => {
  it("hay uno por cada tipo y su kind coincide con la clave", () => {
    expect(Object.keys(FIXTURES).sort()).toEqual([...GRAPHIC_KINDS].sort());
    for (const [k, f] of Object.entries(FIXTURES)) expect(f.kind).toBe(k as GraphicKind);
    expect(ALL_FIXTURES).toHaveLength(12);
  });

  it("son serializables a JSON y vuelven iguales (lo que llegaría por el WebSocket)", () => {
    for (const f of ALL_FIXTURES) expect(JSON.parse(JSON.stringify(f))).toEqual(f);
  });

  it("clasificación coherente: 20 equipos, puntos = 3G+E, DG = GF−GC, orden y posiciones", () => {
    const rows = standingsFull.rows;
    expect(rows).toHaveLength(20);
    rows.forEach((r, i) => {
      expect(r.pos).toBe(i + 1);
      expect(r.points).toBe(r.won * 3 + r.drawn);
      expect(r.gd).toBe(r.gf - r.ga);
      expect(r.played).toBe(r.won + r.drawn + r.lost);
      if (i > 0) expect(rows[i - 1]!.points).toBeGreaterThanOrEqual(r.points);
    });
    expect(rows.filter((r) => r.highlight).map((r) => r.team.id).sort()).toEqual(["barcelona", "valladolid"]);
  });

  it("percentiles entre 0 y 100 y 4-6 stats en la ficha", () => {
    const s = FIXTURES.player_card.stats;
    expect(s.length).toBeGreaterThanOrEqual(4);
    expect(s.length).toBeLessThanOrEqual(6);
    for (const x of s) expect(x.percentile! >= 0 && x.percentile! <= 100).toBe(true);
  });

  it("coordenadas dentro del campo 105×68", () => {
    const inside = (x: number, y: number) => x >= 0 && x <= 105 && y >= 0 && y <= 68;
    for (const s of FIXTURES.shot_map.shots) expect(inside(s.x, s.y)).toBe(true);
    for (const n of FIXTURES.pass_network.nodes) expect(inside(n.x, n.y)).toBe(true);
    for (const a of FIXTURES.connection.arrows) {
      expect(inside(a.x, a.y)).toBe(true);
      expect(inside(a.end_x, a.end_y)).toBe(true);
    }
    expect(FIXTURES.pass_network.nodes).toHaveLength(11);
    const h = FIXTURES.heat_map;
    expect(h.grid).toHaveLength(h.cols * h.rows);
    expect(Math.max(...h.grid)).toBeCloseTo(1);
  });

  it("las aristas de la red apuntan a nodos existentes", () => {
    const ids = new Set(FIXTURES.pass_network.nodes.map((n) => n.player.id));
    for (const e of FIXTURES.pass_network.edges) {
      expect(ids.has(e.a)).toBe(true);
      expect(ids.has(e.b)).toBe(true);
    }
  });

  it("todo es demostración: cifras inventadas", () => {
    // La marca demo_data vive en Graphic, no en el payload; esta prueba documenta la convención.
    expect(FIXTURES.player_card.scope.season).toBe("2024-25");
  });
});
