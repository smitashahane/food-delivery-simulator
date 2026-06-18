import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/orders": "http://api:5000",
      "/stream": "http://api:5000",
      "/api":    "http://api:5000",
      "/metrics":"http://api:5000",
    },
  },
});
