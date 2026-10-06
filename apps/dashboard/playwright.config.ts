import { loadEnvConfig } from "@next/env";
import { defineConfig } from "@playwright/test";

loadEnvConfig(process.cwd());

const baseURL = process.env.E2E_BASE_URL || "http://localhost:3000";
const isRemote = baseURL.startsWith("https://");

export default defineConfig({
  testDir: "./e2e",
  timeout: 300_000,
  reporter: [["html", { open: "never" }]],
  expect: { timeout: 90_000 },
  use: {
    baseURL,
    headless: !!process.env.CI,
    viewport: { width: 1280, height: 800 },
  },
  ...(isRemote
    ? {}
    : {
        webServer: {
          command: "npm run dev",
          url: "http://localhost:3000/",
          reuseExistingServer: !process.env.CI,
        },
      }),
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
