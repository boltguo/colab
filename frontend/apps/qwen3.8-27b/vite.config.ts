import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: path.resolve(__dirname, "../../dist/qwen3.8-27b"),
    emptyOutDir: true,
    target: "es2022",
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (/\/(?:@shikijs|shiki|oniguruma[^/]*|regex[^/]*)\//.test(id)) return undefined;
          if (id.includes("node_modules")) {
            return "vendor";
          }
          return undefined;
        },
      },
    },
  },
  server: {
    port: 5175,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8188",
        changeOrigin: true,
        ws: true,
      },
      "/v1": {
        target: "http://127.0.0.1:8188",
        changeOrigin: true,
      },
      "/docs": {
        target: "http://127.0.0.1:8188",
        changeOrigin: true,
      },
      "/openapi.json": {
        target: "http://127.0.0.1:8188",
        changeOrigin: true,
      },
    },
  },
});
