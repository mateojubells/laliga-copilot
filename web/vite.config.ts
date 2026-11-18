import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// El backend (FastAPI) escucha en 8765. La galería NO depende de él: solo el operador y /program lo usarán.
const BACKEND = "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: BACKEND, changeOrigin: true },
      "/ws": { target: BACKEND, ws: true, changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
