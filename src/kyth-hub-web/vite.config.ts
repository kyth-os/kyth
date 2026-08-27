import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Local-only app: the Python backend binds 127.0.0.1 (see kyth-installer's
// server.py for the pattern this will follow) and this dev server proxies
// /api to it once that backend exists. No CDN, no external fetches — the
// built dist/ ships as static files inside the kyth_welcome package, same
// as kyth-installer's webui/ package-data today.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8642",
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
