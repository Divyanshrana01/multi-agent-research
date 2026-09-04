import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // dev only. the browser talks to :5173 and /api is forwarded to FastAPI,
    // so there's no CORS in development — and none in production either, where
    // FastAPI serves these built files from its own origin.
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    // a stack trace from a live demo is worth the extra files
    sourcemap: true,
  },
});
