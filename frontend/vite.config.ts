import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// v0.2 shell: static file serving for dev/preview. Live broker transport
// (loopback WS) lands with the runtime broker in v0.3.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
  },
  preview: {
    port: 4173,
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  } as never,
});
