import { describe, expect, it } from "vitest";

// Un prefijo de contenedor que no existe falla en silencio (situation pintó sus cifras a 18 px porque el Panel llevaba
// `sit` y el CSS decía `.si .si__fig-v`). Esta prueba lee cada .css y exige que el .tsx pinte esa clase.
const raw = (m: Record<string, unknown>) => Object.entries(m).map(([k, v]) => [k.replace("./", ""), v as string] as const);
const cssFiles = raw(import.meta.glob("./*.css", { query: "?raw", import: "default", eager: true }));
const sources = raw(import.meta.glob(["./*.tsx", "!./*.test.tsx"], { query: "?raw", import: "default", eager: true }));
const allSource = sources.map(([, s]) => s).join("\n");

/** Bloques usados como contenedor: `.X .X__…` (el contenedor tiene que existir). */
export function containerPrefixes(css: string): string[] {
  const out = new Set<string>();
  for (const m of css.matchAll(/\.([a-z][\w-]*) [^{,]*?\.\1__/g)) out.add(m[1]!);
  return [...out];
}
/** Bloques usados a secas: `.X__…` (el bloque tiene que aparecer en algún className). */
export function blockPrefixes(css: string): string[] {
  const out = new Set<string>();
  for (const m of css.matchAll(/\.([a-z][\w]*)__[\w-]+/g)) out.add(m[1]!);
  return [...out];
}
/** ¿Algún className del fuente contiene `X` como clase suelta (en una cadena o en una plantilla)? */
export function hasClass(src: string, x: string): boolean {
  const re = new RegExp(`class(?:Name)?=(?:"[^"]*|\\{\`[^\`]*|\\{"[^"]*)(?<![\\w-])${x}(?![\\w-])`);
  return re.test(src);
}

describe("prefijos de clase de los .css de grafismos", () => {
  it("hay hojas que comprobar", () => expect(cssFiles.length).toBeGreaterThan(10));

  for (const [f, raw] of cssFiles) {
    const css = raw.replace(/\/\*[\s\S]*?\*\//g, "");
    it(`${f}: todo contenedor \`.X .X__…\` tiene su clase X en el .tsx`, () => {
      for (const x of containerPrefixes(css)) expect(hasClass(allSource, x), `.${x} (usado como contenedor en ${f}) no se pinta en ningún className`).toBe(true);
    });
    it(`${f}: todo bloque \`.X__…\` se usa en algún .tsx`, () => {
      for (const x of blockPrefixes(css)) expect(allSource.includes(`${x}__`), `.${x}__… de ${f} no aparece en ningún .tsx`).toBe(true);
    });
  }

  it("la prueba detecta el fallo original (className=\"sit\" frente a .si .si__fig-v)", () => {
    expect(containerPrefixes(".si .si__fig-v { font-size: 72px }")).toEqual(["si"]);
    expect(hasClass('<Panel className="sit">', "si")).toBe(false);
    expect(hasClass('<Panel className="sit si">', "si")).toBe(true);
    expect(hasClass("<Panel className={`h2h${full ? 1 : 2}`}>", "h2h")).toBe(true);
  });
});
