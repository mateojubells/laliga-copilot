import type { ComponentType } from "react";
import type { GraphicKind, PayloadOf } from "../contracts";

/** Props de cualquier grafismo: el payload tipado y si es dato de demostración (Graphic.demo_data). */
export interface GraphicProps<K extends GraphicKind = GraphicKind> {
  payload: PayloadOf<K>;
  demoData: boolean;
  /**
   * Vista de operador (true) frente a la de antena (false, por defecto). En antena no se pinta NINGÚN estado de
   * moderación (✓, lápiz, aro de "sin confirmar", eventos descartados). Hoy solo lo usa la línea de tiempo.
   */
  editorial?: boolean;
  /** Variante de formato del grafismo (h2h: "live" = tercio inferior, "full" = con últimos partidos). */
  variant?: string;
}

export type GraphicComponent<K extends GraphicKind = GraphicKind> = ComponentType<GraphicProps<K>>;
