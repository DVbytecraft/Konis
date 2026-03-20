import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/__tests__/setup.ts"],
    // Exclut les fichiers Next.js qui ne peuvent pas tourner hors du runtime Next,
    // et les tests Playwright (tests/e2e/**) qui utilisent une API incompatible avec Vitest
    exclude: ["node_modules", ".next", "**/*.e2e.*", "tests/e2e/**"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
