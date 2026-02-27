import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../frontend-dist",
    emptyOutDir: true,
  },
  resolve: {
    alias: {
      "~": path.resolve(__dirname, "src"),
    },
  },
  server: {
    proxy: {
      "/ws": {
        target: "ws://localhost:3457",
        ws: true,
      },
      "/api": {
        target: "http://localhost:3457",
        changeOrigin: true,
      },
    },
  },
});
