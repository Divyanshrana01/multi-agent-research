import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Kept separate from vite.config.ts so the test environment is explicit —
// components need a real DOM, and the default node environment has no
// localStorage, which the API client reads on every request.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
    css: true, // so CSS module class names resolve instead of coming back undefined
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
