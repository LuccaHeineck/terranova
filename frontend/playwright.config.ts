import { defineConfig, devices } from '@playwright/test'

/**
 * Smoke tests of the running app (e2e/). They drive the real backend, which needs the processed rasters and raw
 * gauge/extent files in data/ (see data/README.md).
 *
 * By default both servers are started here (or reused, if already running): uvicorn from backend/.venv on :8000
 * and the Vite dev server on :5173. To test another deployment instead, e.g. `docker compose up`, point
 * E2E_BASE_URL at its frontend and no server is started.
 */
const external = process.env.E2E_BASE_URL
const python = process.env.E2E_PYTHON ?? (process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python')

export default defineConfig({
  testDir: './e2e',
  // One backend serves every test, and a temporal run is CPU-bound: parallel runs would slow each other down.
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: {
    baseURL: external ?? 'http://localhost:5173',
    locale: 'en-US',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: external
    ? undefined
    : [
        {
          command: `${python} -m uvicorn api.main:app --port 8000`,
          cwd: '../backend',
          url: 'http://localhost:8000/health',
          reuseExistingServer: true,
          timeout: 60_000,
        },
        {
          command: 'npm run dev -- --port 5173 --strictPort',
          url: 'http://localhost:5173',
          reuseExistingServer: true,
          timeout: 60_000,
        },
      ],
})
