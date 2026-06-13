import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In production the app is served behind nginx, which proxies /api to the
// backend. In dev, Vite proxies /api to a locally running backend on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
