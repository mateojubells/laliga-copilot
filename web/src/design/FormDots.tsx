import "./Tiles.css";

export type FormResult = "W" | "D" | "L";
const ES: Record<FormResult, string> = { W: "V", D: "E", L: "D" };
const NAME: Record<FormResult, string> = { W: "victoria", D: "empate", L: "derrota" };

/** Forma reciente: V/E/D. Orden: de más antiguo (izquierda) a más reciente (derecha). `square` = cuadrados sin letra. */
export function FormDots({ form, size = 36, square = false }: { form: readonly FormResult[]; size?: number; square?: boolean }) {
  return (
    <span className={`formdots${square ? " formdots--sq" : ""}`} role="img" aria-label={`Forma: ${form.map((f) => NAME[f]).join(", ")}`}>
      {form.map((f, i) => (
        <span
          key={i}
          className={`formdots__dot formdots__dot--${f}`}
          style={{ width: size, height: size, lineHeight: `${size}px` }}
        >
          {ES[f]}
        </span>
      ))}
    </span>
  );
}
