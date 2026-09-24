import { resolve } from "node:path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

const api = process.env.VITE_API_PROXY ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      input: {
        landing: resolve(__dirname, "index.html"),
        app: resolve(__dirname, "app/index.html"),
      },
    },
  },
  server: {
    proxy: { "/api": api, "/tg": api },
  },
  preview: {
    proxy: { "/api": api, "/tg": api },
  },
});
