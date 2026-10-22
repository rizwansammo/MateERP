import { defineConfig } from '@playwright/test';
import baseConfig from './playwright.config';

// Override only the Phase 7D harness web-server command, so it never listens
// on a public interface during isolated browser tests on a shared VPS.
export default defineConfig(baseConfig, {
  webServer: {
    command: 'npm run start -- --hostname 127.0.0.1',
    url: 'http://127.0.0.1:3100/login',
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
