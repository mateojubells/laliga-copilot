import type { ComponentType } from "react";
import type { Graphic } from "../contracts";
import { GRAPHICS, PLACEMENT } from "./registry";

/**
 * Pinta un grafismo en su sitio del lienzo 1920×1080. Usado por la galería, /program y el operador.
 * `editorial` = vista de operador (estados de moderación visibles); por defecto es la vista de antena.
 */
export function GraphicView({
  graphic,
  editorial = false,
  variant,
}: {
  graphic: Pick<Graphic, "payload" | "demo_data">;
  editorial?: boolean;
  variant?: string;
}) {
  const { payload } = graphic;
  // El registro está tipado por kind; aquí se pierde la correlación kind↔payload (limitación de TypeScript).
  const Component = GRAPHICS[payload.kind] as ComponentType<{ payload: typeof payload; demoData: boolean; editorial?: boolean; variant?: string }>;
  return (
    <div style={{ position: "absolute", ...PLACEMENT[payload.kind] }} data-kind={payload.kind}>
      <Component payload={payload} demoData={graphic.demo_data ?? true} editorial={editorial} variant={variant} />
    </div>
  );
}
