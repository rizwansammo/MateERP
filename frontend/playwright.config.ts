import { defineConfig, devices } from '@playwright/test';

/*
 * End-to-end tests run against the production build (`npm run build` first)
 * and the real backend from Docker Compose (`docker compose up -d`). They
 * share one dev database, so they run serially.
 */
const PORT = 3100;
const ADMIN_STATE = 'tests/e2e/.auth/admin.json';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  // The first renders after a fresh `next start` can exceed the default 5 s.
  expect: { timeout: 10_000 },
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: [['list']],
  globalSetup: './tests/e2e/global-setup.ts',
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: 'retain-on-failure',
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    { name: 'setup', testMatch: /auth\.setup\.ts/ },
    {
      name: 'chromium',
      dependencies: ['setup'],
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 }, storageState: ADMIN_STATE },
    },
  ],
  webServer: {
    command: 'npm run start',
    url: `http://localhost:${PORT}/login`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
