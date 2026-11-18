// Genera src/contracts/contracts.ts desde el JSON Schema del backend (copilot/graphics/payloads.py).
// Se ejecuta desde web/; el backend se invoca desde la raíz del repo.
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../..");
const py = resolve(root, ".venv/bin/python");
const out = resolve(here, "../src/contracts/contracts.ts");

const raw = execFileSync(py, ["-m", "copilot.graphics.payloads"], { cwd: root, encoding: "utf8" });
const schema = JSON.parse(raw);

// Pydantic añade `title` a cada propiedad (Kind, X, Headline1...) y json-schema-to-typescript los convierte en alias
// basura. Se quitan; cada definición conserva su nombre. Además, `prefixItems` (tuplas, draft 2020-12) se traduce al
// `items: [...]` que entiende el generador.
function clean(node) {
  if (Array.isArray(node)) return node.forEach(clean);
  if (node === null || typeof node !== "object") return;
  if (typeof node.title === "string") delete node.title; // (una PROPIEDAD llamada "title" no es un título)
  if (node.prefixItems) {
    node.items = node.prefixItems;
    node.minItems = node.prefixItems.length;
    node.maxItems = node.prefixItems.length;
    delete node.prefixItems;
  }
  for (const v of Object.values(node)) clean(v);
}
for (const [name, def] of Object.entries(schema.$defs)) {
  clean(def);
  def.title = name;
  // `kind` tiene valor por defecto en pydantic y por eso no figura como obligatorio, pero siempre viaja en el JSON
  // (es el discriminador). Se marca obligatorio para que TypeScript pueda discriminar la unión.
  if (def.properties?.kind?.const && name !== "Graphic") {
    def.required = [...new Set([...(def.required ?? []), "kind"])];
  }
}
delete schema.title;
const ts = await compile(schema, "CopilotContracts", {
  bannerComment:
    "/* AUTO-GENERADO por `npm run gen:contracts` desde copilot/graphics/payloads.py. NO EDITAR A MANO. */",
  unreachableDefinitions: true,
  additionalProperties: false,
  style: { singleQuote: false, printWidth: 110 },
});
writeFileSync(out, ts);
console.log(`escrito ${out} (${ts.length} bytes)`);
