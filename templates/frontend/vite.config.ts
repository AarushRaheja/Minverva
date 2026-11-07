import { defineConfig } from "vite";

// `npm run dev` proxies the API, so the browser sees one origin, as it does in production.
export default defineConfig({
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
