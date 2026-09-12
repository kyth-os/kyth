import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Local-only React/Tauri frontend. Production embeds the built dist/ directly
// in the Rust shell; no Python backend or second UI package is part of the Hub
// runtime path. The proxy is retained only for installer-adjacent local work.
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
    // The production frontend is embedded in the Tauri binary.  Source maps
    // add several megabytes to that payload but are not used by normal Hub
    // launches; retain them only in local development through Vite's dev
    // tooling instead of shipping them to every KythOS desktop.
    sourcemap: false,
  },
});
