/**
 * AudioWorklet: micro → PCM 16 bits little-endian, 16 000 Hz, mono, en trozos de 100 ms (1600 muestras = 3200 bytes).
 *
 * Remuestreo: promedio por áreas (filtro de caja). Cada muestra de salida es la media de las muestras de entrada que
 * caen en su ventana de `inRate/16000` muestras (con pesos fraccionarios en los bordes). Es lineal, sin estado oculto
 * entre bloques y actúa como paso bajo sencillo (antes de decimar), así que evita el aliasing de coger una de cada N.
 * Con 48 kHz es exactamente la media de cada 3 muestras; con 44,1 kHz (razón 2,75625) reparte los bordes.
 * Si el dispositivo da ≤ 16 kHz no hay nada que decimar: la razón vale 1 o menos y se repite la muestra.
 * Varios canales se mezclan a mono (media).
 *
 * Mensajes al hilo principal: { pcm: ArrayBuffer (Int16 LE), peak: number (0..1, pico del trozo) }.
 */
const TARGET_RATE = 16000;
const CHUNK = 1600;

class PcmChunker {
  constructor(inRate, onChunk) {
    this.ratio = inRate / TARGET_RATE;
    this.filled = 0; // cuánto de la ventana actual (en muestras de entrada) ya está acumulado
    this.acc = 0;
    this.out = new Int16Array(CHUNK);
    this.n = 0;
    this.peak = 0;
    this.onChunk = onChunk;
  }

  /** Procesa un bloque mono en float [-1, 1]. */
  push(x) {
    const r = this.ratio;
    for (let i = 0; i < x.length; i++) {
      let w = 1;
      const v = x[i];
      while (w > 1e-9) {
        const take = Math.min(w, r - this.filled);
        this.acc += v * take;
        this.filled += take;
        w -= take;
        if (this.filled >= r - 1e-9) {
          this.emit(this.acc / r);
          this.acc = 0;
          this.filled = 0;
        }
      }
    }
  }

  emit(f) {
    const c = Math.max(-1, Math.min(1, f));
    const a = Math.abs(c);
    if (a > this.peak) this.peak = a;
    this.out[this.n++] = Math.round(c < 0 ? c * 32768 : c * 32767);
    if (this.n === CHUNK) {
      const buf = this.out.buffer;
      const peak = this.peak;
      this.out = new Int16Array(CHUNK);
      this.n = 0;
      this.peak = 0;
      this.onChunk(buf, peak);
    }
  }
}

if (typeof registerProcessor === "function") {
  class PcmProcessor extends AudioWorkletProcessor {
    constructor() {
      super();
      this.chunker = new PcmChunker(sampleRate, (pcm, peak) => this.port.postMessage({ pcm, peak }, [pcm]));
      this.mono = new Float32Array(128);
    }

    process(inputs) {
      const ch = inputs[0];
      if (!ch || !ch.length) return true;
      const n = ch[0].length;
      if (ch.length === 1) {
        this.chunker.push(ch[0]);
      } else {
        if (this.mono.length < n) this.mono = new Float32Array(n);
        for (let i = 0; i < n; i++) {
          let s = 0;
          for (let c = 0; c < ch.length; c++) s += ch[c][i];
          this.mono[i] = s / ch.length;
        }
        this.chunker.push(this.mono.subarray(0, n));
      }
      return true;
    }
  }
  registerProcessor("pcm-16k", PcmProcessor);
}

if (typeof globalThis !== "undefined") globalThis.__PcmChunker = PcmChunker; // para los tests
