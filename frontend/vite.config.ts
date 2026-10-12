import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const port = env.OBS_PORT || "8080";
  const host = env.OBS_HOST || "127.0.0.1";

  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": `http://${host}:${port}`,
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts",
    },
  };
});
