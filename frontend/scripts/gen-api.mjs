import { execFileSync } from "node:child_process";
import { loadEnv } from "vite";

const env = loadEnv("development", process.cwd(), "");
const host = env.OBS_HOST || "127.0.0.1";
const port = env.OBS_PORT || "8080";
const url = `http://${host}:${port}/openapi.json`;

execFileSync(
  "npx",
  ["openapi-typescript", url, "-o", "src/api/schema.ts"],
  { stdio: "inherit", cwd: process.cwd() },
);
