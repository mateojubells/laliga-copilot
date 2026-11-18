import { describe, expect, it } from "vitest";
import src from "../../../public/pcm-worklet.js?raw";
import { isTooQuiet, levelToMeter, peakOf } from "./meter";

type Chunker = { push(x: Float32Array | number[]): void };
type Ctor = new (rate: number, cb: (pcm: ArrayBuffer, peak: number) => void) => Chunker;

function load(): Ctor {
  new Function(src)(); // el worklet se autoexporta en globalThis.__PcmChunker (sin registerProcessor fuera de un worklet)
  return (globalThis as unknown as { __PcmChunker: Ctor }).__PcmChunker;
}

function run(rate: number, input: Float32Array, block = 128) {
  const chunks: Int16Array[] = [];
  const peaks: number[] = [];
  const c = new (load())(rate, (pcm, peak) => { chunks.push(new Int16Array(pcm)); peaks.push(peak); });
  for (let i = 0; i < input.length; i += block) c.push(input.subarray(i, Math.min(input.length, i + block)));
  return { chunks, peaks };
}

describe("remuestreo a 16 kHz mono Int16", () => {
  it("48 kHz → 16 kHz: 4800 muestras (100 ms) dan un trozo de 1600 muestras = 3200 bytes", () => {
    const { chunks } = run(48000, new Float32Array(4800).fill(0.5));
    expect(chunks).toHaveLength(1);
    expect(chunks[0]).toHaveLength(1600);
    expect(chunks[0].byteLength).toBe(3200);
    expect(chunks[0][0]).toBe(16384); // 0.5 · 32767 redondeado
    expect(chunks[0][1599]).toBe(16384);
  });

  it("48 kHz: cada salida es la media de 3 entradas (rampa conocida)", () => {
    const x = new Float32Array(4800);
    for (let i = 0; i < x.length; i++) x[i] = (i % 3 === 0 ? 0.3 : i % 3 === 1 ? 0.6 : 0.9); // media 0.6
    const { chunks } = run(48000, x);
    for (const v of [chunks[0][0], chunks[0][800], chunks[0][1599]]) expect(Math.abs(v - 0.6 * 32767)).toBeLessThanOrEqual(1);
  });

  it("atenúa lo que el decimado sin filtro dejaría pasar como alias (3 kHz a 48 kHz → 16 kHz)", () => {
    // 24 kHz (Nyquist de la entrada) alterna +1/−1: sin filtro habría salido ±1; promediando casi desaparece
    const x = new Float32Array(4800);
    for (let i = 0; i < x.length; i++) x[i] = i % 2 ? -1 : 1;
    const { chunks } = run(48000, x);
    const peak = Math.max(...Array.from(chunks[0]).map(Math.abs));
    expect(peak).toBeLessThan(0.4 * 32767);
  });

  it("el tamaño de bloque de entrada no cambia el resultado (estado entre bloques)", () => {
    const x = new Float32Array(9600).map((_, i) => Math.sin(i / 7) * 0.8);
    const a = run(48000, x, 128).chunks;
    const b = run(48000, x, 1000).chunks;
    expect(a).toHaveLength(2);
    expect(Array.from(b[1])).toEqual(Array.from(a[1]));
  });

  it("44,1 kHz (razón no entera): 100 ms de entrada ≈ 1600 muestras y el valor constante se conserva", () => {
    const { chunks } = run(44100, new Float32Array(44100).fill(-0.25)); // 1 s
    expect(chunks.length).toBeGreaterThanOrEqual(9);
    expect(chunks[0]).toHaveLength(1600);
    expect(Math.abs(chunks[3][800] - -0.25 * 32768)).toBeLessThanOrEqual(1);
  });

  it("recorta a [−1, 1] y reporta el pico del trozo", () => {
    const { chunks, peaks } = run(16000, new Float32Array(1600).fill(1.5));
    expect(chunks[0][0]).toBe(32767);
    expect(peaks[0]).toBe(1);
  });
});

describe("medidor", () => {
  it("peakOf y escala dB", () => {
    expect(peakOf([0, -0.4, 0.2])).toBeCloseTo(0.4);
    expect(levelToMeter(0)).toBe(0);
    expect(levelToMeter(1)).toBe(1);
    expect(levelToMeter(0.001)).toBeCloseTo(0, 5); // −60 dB
    expect(levelToMeter(0.1)).toBeCloseTo(40 / 60, 3);
  });
  it("demasiado bajo por debajo de 0,02", () => {
    expect(isTooQuiet(0.005)).toBe(true);
    expect(isTooQuiet(0.2)).toBe(false);
  });
});
