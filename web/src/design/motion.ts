import type { Variants } from "framer-motion";

/** Copia en JS de los tokens de movimiento (framer-motion no lee variables CSS). Mantener sincronizado con tokens.css. */
export const MOTION = {
  inMs: 400,
  outMs: 250,
  slide: 48,
  /** Escalonado entre elementos hermanos (s). */
  stagger: 0.045,
  easeOut: [0.16, 1, 0.3, 1] as [number, number, number, number],
  easeIn: [0.5, 0, 0.75, 0] as [number, number, number, number],
};

/** Borde del lienzo desde el que entra un panel: el borde donde está anclado. */
export type Edge = "left" | "right" | "bottom" | "top";

const offsetFor = (from: Edge, d: number) =>
  from === "left" ? { x: -d } : from === "right" ? { x: d } : from === "bottom" ? { y: d } : { y: -d };

/**
 * Entrada: deslizar + fundido (~400 ms, ease-out) DESDE el borde donde está anclado el panel (derecha para la
 * comparativa, abajo para los tercios inferiores…). Salida: ~250 ms hacia el mismo borde.
 */
export function enterVariants(from: Edge = "left"): Variants {
  return {
    hidden: { opacity: 0, ...offsetFor(from, MOTION.slide) },
    shown: {
      opacity: 1,
      x: 0,
      y: 0,
      // escalonado de los hijos con variantes (itemVariants, popVariants…): ~45 ms entre elementos
      transition: { duration: MOTION.inMs / 1000, ease: MOTION.easeOut, staggerChildren: MOTION.stagger, delayChildren: 0.12 },
    },
    exit: { opacity: 0, ...offsetFor(from, MOTION.slide / 2), transition: { duration: MOTION.outMs / 1000, ease: MOTION.easeIn } },
  };
}

/** Entrada por defecto (desde la izquierda). */
export const panelVariants: Variants = enterVariants("left");

/** Marcador: barrido horizontal (clip-path 350 ms) en vez de deslizar. */
export const wipeVariants: Variants = {
  hidden: { opacity: 1, clipPath: "inset(0 100% 0 0)" },
  shown: { opacity: 1, clipPath: "inset(0 0% 0 0)", transition: { duration: 0.35, ease: MOTION.easeOut } },
  exit: { opacity: 0, transition: { duration: MOTION.outMs / 1000, ease: MOTION.easeIn } },
};

/** Para elementos que entran desde abajo (scorebug, barras inferiores). */
export const riseVariants: Variants = {
  hidden: { opacity: 0, y: MOTION.slide },
  shown: { opacity: 1, y: 0, transition: { duration: MOTION.inMs / 1000, ease: MOTION.easeOut } },
  exit: { opacity: 0, y: MOTION.slide / 2, transition: { duration: MOTION.outMs / 1000, ease: MOTION.easeIn } },
};

/** Elemento de contenido (bloque de datos, fila, tile): sube 16 px y aparece. Hereda "hidden/shown" del grafismo. */
export const itemVariants: Variants = {
  hidden: { opacity: 0, y: 16 },
  shown: { opacity: 1, y: 0, transition: { duration: MOTION.inMs / 1000, ease: MOTION.easeOut } },
};

/** Fila que se despliega desde su izquierda (barras, filas de lista). `custom` = índice para el escalonado. */
export const rowVariants: Variants = {
  hidden: { opacity: 0, x: -24 },
  shown: (i: number = 0) => ({
    opacity: 1,
    x: 0,
    transition: { duration: MOTION.inMs / 1000, ease: MOTION.easeOut, delay: 0.1 + i * MOTION.stagger },
  }),
};

/** Aparición con rebote suave para elementos SVG (nodos, tiros, iconos). `custom` = índice. */
export const popVariants: Variants = {
  hidden: { opacity: 0, scale: 0.4 },
  shown: (i: number = 0) => ({
    opacity: 1,
    scale: 1,
    transition: { duration: MOTION.inMs / 1000, ease: MOTION.easeOut, delay: 0.1 + i * MOTION.stagger },
  }),
};

/** Trazo que se dibuja (pathLength = stroke-dashoffset). `custom` = índice. */
export const drawVariants: Variants = {
  hidden: { pathLength: 0, opacity: 0 },
  shown: (i: number = 0) => ({
    pathLength: 1,
    opacity: 1,
    transition: { duration: 0.7, ease: MOTION.easeOut, delay: 0.15 + i * MOTION.stagger },
  }),
};

/** Punta de flecha: aparece cuando el trazo ya casi llegó. */
export const headVariants: Variants = {
  hidden: { opacity: 0 },
  shown: (i: number = 0) => ({ opacity: 1, transition: { duration: 0.2, delay: 0.55 + i * MOTION.stagger } }),
};

/** Barra que crece desde su origen (transformOrigin en el estilo). `custom` = índice. */
export const growVariants: Variants = {
  hidden: { scaleX: 0 },
  shown: (i: number = 0) => ({
    scaleX: 1,
    transition: { duration: 0.6, ease: MOTION.easeOut, delay: 0.2 + i * MOTION.stagger },
  }),
};
