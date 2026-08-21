import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.TRADEFRAME_FRONTEND_PORT ?? 5173),
    strictPort: true,
    proxy: {
      "/api": process.env.TRADEFRAME_BACKEND_URL ?? "http://127.0.0.1:8000"
    }
  }
});
