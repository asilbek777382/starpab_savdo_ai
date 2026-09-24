import { resolve } from "node:path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig, type Connect, type Plugin } from "vite";

const api = process.env.VITE_API_PROXY ?? "http://localhost:8000";

/** /app/* marshrutlari panel SPA'siga (app/index.html) tushadi — prod'da buni nginx qiladi. */
function appFallback(): Plugin {
  const rewrite: Connect.NextHandleFunction = (req, _res, next) => {
    const url = req.url ?? "";
    if (url.startsWith("/app") && !url.startsWith("/app/index.html") && !/\.[a-z0-9]+(\?|$)/i.test(url)) {
      req.url = "/app/index.html";
    }
    next();
  };
  return {
    name: "app-spa-fallback",
    configureServer: (server) => void server.middlewares.use(rewrite),
    configurePreviewServer: (server) => void server.middlewares.use(rewrite),
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), appFallback()],
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
