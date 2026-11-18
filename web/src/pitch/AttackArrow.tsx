import { motion } from "framer-motion";
import { itemVariants } from "../design/motion";
import { usePitch } from "./context";

/**
 * Sentido de ataque: plantilla común de los cuatro grafismos de campo. Un solo rótulo ("ATAQUE →"), con la flecha de 160 px,
 * FUERA del césped, en la banda superior del campo (`topBand` de <Pitch>) y alineado con su borde izquierdo. Si el campo no
 * tiene banda superior (usos antiguos) se dibuja sobre el césped, en la banda inferior.
 */
export const ATTACK_LABEL = "ATAQUE";
/** Largo de la flecha (px): el mismo en los cuatro grafismos de campo. */
export const ATTACK_ARROW_LEN = 160;

export function AttackArrow() {
  const { x, y, top } = usePitch();
  const inBand = top >= 36;
  const textW = ATTACK_LABEL.length * 14.5;
  const x1 = Math.max(0, x(0)) + 4;
  const lineFrom = x1 + textW + 14;
  const x2 = lineFrom + ATTACK_ARROW_LEN - 10;
  const cy = inBand ? top / 2 : y(63.4);
  return (
    <motion.g data-layer="attack-arrow" variants={itemVariants}>
      <text
        x={x1}
        y={cy}
        dy="0.34em"
        fontFamily="var(--font-display)"
        fontWeight={700}
        fontSize={24}
        letterSpacing="0.1em"
        fill="#fff"
        fillOpacity={0.92}
        stroke={inBand ? undefined : "rgba(4,8,14,0.85)"}
        strokeWidth={inBand ? undefined : 6}
        paintOrder="stroke"
      >
        {ATTACK_LABEL}
      </text>
      <line x1={lineFrom} y1={cy} x2={x2 - 4} y2={cy} stroke="#fff" strokeOpacity={0.92} strokeWidth={4} strokeLinecap="round" />
      <polygon points={`${x2 + 10},${cy} ${x2 - 10},${cy - 12} ${x2 - 10},${cy + 12}`} fill="#fff" fillOpacity={0.92} strokeLinejoin="round" />
    </motion.g>
  );
}
