import { defineConfig } from '@playwright/test';

// UI tests with a mocked backend (no DigiKey credentials or API quota needed).
// Uses the locally installed Chrome; run `npx playwright install chromium` and drop `channel` if you don't have it.
// WSL with networkingMode=mirrored: probing a closed port hangs ~2 min before Playwright starts the server itself.
// Start it first (`npx vite --host 127.0.0.1 --port 5174`) and it is reused, so the run takes seconds.
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:5174/digikey-bom-converter/',
    channel: 'chrome',
    headless: true,
  },
  webServer: {
    command: 'npx vite --host 127.0.0.1 --port 5174 --strictPort',
    url: 'http://127.0.0.1:5174/digikey-bom-converter/',
    reuseExistingServer: !process.env.CI,
  },
});
