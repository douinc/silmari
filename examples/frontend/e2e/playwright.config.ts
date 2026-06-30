import { defineConfig, devices } from "@playwright/test";

const PORT = 8123;

// Full-stack e2e: Playwright boots `silmari serve --ui --demo-data` (seeded DuckDB + the example
// bots + the reference UI, same-origin) and drives the real browser against it. The webServer cwd
// is the repo root (this config lives at examples/frontend/e2e/).
export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  use: { baseURL: `http://127.0.0.1:${PORT}`, trace: "on-first-retry" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `uv run silmari serve --ui examples/frontend --demo-data --bots-dir examples/bots --port ${PORT}`,
    cwd: "../../..",
    url: `http://127.0.0.1:${PORT}/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 90_000,
  },
});
