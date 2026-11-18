import type { ScaleLinear } from "d3-scale";
import { createContext, useContext } from "react";

/** Lo que las capas reciben del campo: escalas metros → píxeles del viewBox (origen de datos abajo-izquierda). */
export interface PitchCtx {
  /** x: 0-105 m → px (hacia la derecha, el ataque va hacia x creciente) */
  x: ScaleLinear<number, number>;
  /** y: 0-68 m → px (invertida: y=0 queda ABAJO) */
  y: ScaleLinear<number, number>;
  /** píxeles por metro */
  k: number;
  width: number;
  height: number;
  /** margen alrededor del campo */
  pad: number;
  /** banda libre bajo el campo (leyendas) */
  bottom: number;
  /** banda libre sobre el campo (sentido de ataque) */
  top: number;
  accent: string;
}

export const PitchContext = createContext<PitchCtx | null>(null);

export function usePitch(): PitchCtx {
  const c = useContext(PitchContext);
  if (!c) throw new Error("Las capas del campo deben ir dentro de <Pitch>");
  return c;
}
