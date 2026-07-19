import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: Vite on :5173 proxies /api -> FastAPI on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // bind 0.0.0.0 (IPv4 + IPv6) so localhost always resolves
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        // 127.0.0.1 avoids IPv4/IPv6 resolution ambiguity for the backend too
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
