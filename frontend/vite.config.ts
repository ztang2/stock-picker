import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../static/dist",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/scan": "http://localhost:8000",
      "/stock": "http://localhost:8000",
      "/entry": "http://localhost:8000",
      "/dcf": "http://localhost:8000",
      "/comps": "http://localhost:8000",
      "/earnings": "http://localhost:8000",
      "/momentum": "http://localhost:8000",
      "/review": "http://localhost:8000",
      "/sectors": "http://localhost:8000",
      "/top": "http://localhost:8000",
      "/backtest": "http://localhost:8000",
      "/accuracy": "http://localhost:8000",
      "/alerts": "http://localhost:8000",
      "/portfolio": "http://localhost:8000",
      "/risk": "http://localhost:8000",
      "/profit": "http://localhost:8000",
      "/sizing": "http://localhost:8000",
      "/snapshots": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
