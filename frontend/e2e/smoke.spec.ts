import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'

// Smoke tests against the real backend (see playwright.config.ts). They check that the app's main paths work
// end to end, not the model's numbers: those are the backend suite's and the validation scripts' job.

async function openApp(page: Page) {
  await page.goto('/?lang=en')
  // The dashed grid outline is drawn once /grids has answered: the app is ready to set up a run.
  await expect(gridOutline(page)).toBeVisible()
}

/** The dark dashed line of the grid outline in the (first) map pane. */
function gridOutline(page: Page): Locator {
  return page.locator('.leaflet-container').first().locator('.leaflet-seed-pane path[stroke-dasharray="6 4"]')
}

async function chooseGrid(page: Page, resolution: 30 | 60 | 90) {
  await page.getByText(`${resolution} m`, { exact: true }).click()
}

/** A seeded pool on the 90m grid: 200 steps, 40 frames, a few seconds. */
async function runSeededPool(page: Page) {
  await chooseGrid(page, 90)
  await page.getByRole('button', { name: /^Start/ }).click()
  await expect(page.getByTestId('timeline-state')).toHaveText('Latest', { timeout: 60_000 })
}

function runStatus(page: Page): Locator {
  return page.locator('header').getByRole('status')
}

test('setup: a seeded pool runs to the end and conserves its volume', async ({ page }) => {
  await openApp(page)
  await runSeededPool(page)

  await expect(runStatus(page)).toHaveText('Done')
  const readout = page.getByTestId('timeline-readout')
  await expect(readout).toContainText('Frame 40/40')
  // The pool is closed: the 400 m of seeded depth is all still there at the last step.
  await expect(readout).toContainText('volume 400.0')
  await expect(page.locator('img.flood-frame')).toHaveCount(1)
})

test('replay: the May 2024 preset opens Compare, and Stop ends it', async ({ page }) => {
  await openApp(page)
  await page.getByRole('button', { name: 'Replay the May 2024 flood' }).click()

  await expect(page.getByRole('button', { name: 'Compare', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('.leaflet-container')).toHaveCount(2)
  await expect(page.getByText('Fast: steady peak extent')).toBeVisible()
  // Gauge-driven frames carry real elapsed time.
  await expect(page.getByTestId('timeline-time')).toBeVisible({ timeout: 60_000 })
  await expect(runStatus(page)).toHaveText('Running')

  await page.getByRole('button', { name: 'Stop', exact: true }).click()
  await expect(runStatus(page)).toHaveText('Stopped')
  await expect(page.getByRole('button', { name: /^Start/ })).toBeVisible()
})

test('seeding: a click inside the grid places the seed, a click outside says why', async ({ page }) => {
  await openApp(page)
  await chooseGrid(page, 90)
  // Zoomed out a step, the grid leaves map on every side of it to click.
  await page.getByRole('button', { name: 'Zoom out' }).first().click()
  await page.waitForTimeout(500)
  const outline = (await gridOutline(page).boundingBox())!

  await page.mouse.click(outline.x + outline.width / 2, outline.y + outline.height / 2)
  await expect(page.getByText('Click the map again to move it; Clear goes back to the lowest point.')).toBeVisible()

  await page.getByRole('button', { name: 'Clear', exact: true }).click()
  await expect(page.getByText('Lowest point of the terrain (default)')).toBeVisible()

  await page.mouse.click(outline.x + outline.width + 30, outline.y + outline.height / 2)
  await expect(page.getByText('Outside the 90 m grid: click inside the dashed outline.')).toBeVisible()
})

test('basemap picker: the choice applies at once and is remembered', async ({ page }) => {
  await openApp(page)
  const satellite = page.getByRole('radio', { name: 'Satellite' })

  await page.getByRole('button', { name: 'Map layers' }).click()
  await satellite.click()
  await expect(satellite).toHaveAttribute('aria-checked', 'true')
  await expect(page.locator('img.leaflet-tile[src*="World_Imagery"]').first()).toBeAttached()

  await page.reload()
  await expect(gridOutline(page)).toBeVisible()
  await page.getByRole('button', { name: 'Map layers' }).click()
  await expect(satellite).toHaveAttribute('aria-checked', 'true')
})

test('timeline: the buffered frames replay, at each speed', async ({ page }) => {
  await openApp(page)
  await runSeededPool(page)
  const state = page.getByTestId('timeline-state')
  const speed = page.getByTestId('timeline-speed')

  await expect(speed).toHaveText('1×')
  await page.getByRole('button', { name: 'Play buffered frames' }).click()
  await expect(state).toHaveText('Replaying')
  await speed.click()
  await expect(speed).toHaveText('4×')
  await speed.click()
  await expect(speed).toHaveText('16×')
  // At 16x the 40 frames are over in well under a second.
  await expect(state).toHaveText('Latest')
  await expect(page.getByTestId('timeline-readout')).toContainText('Frame 40/40')
  // Fades end with one frame on screen, never two.
  await expect(page.locator('img.flood-frame')).toHaveCount(1)

  await speed.click()
  await expect(speed).toHaveText('1×')
})

test.describe('narrow screen', () => {
  test.use({ viewport: { width: 375, height: 800 } })

  test('Compare stacks its panes, fits the grid in each, and keeps the page in the viewport', async ({ page }) => {
    await openApp(page)
    await page.getByRole('button', { name: 'Replay the May 2024 flood' }).click()
    await expect(page.getByRole('button', { name: 'Compare', exact: true })).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByTestId('timeline-time')).toBeVisible({ timeout: 60_000 })

    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375)
    const panes = page.locator('.leaflet-container')
    await expect(panes).toHaveCount(2)
    const top = (await panes.nth(0).boundingBox())!
    const bottom = (await panes.nth(1).boundingBox())!
    expect(bottom.y).toBeGreaterThanOrEqual(top.y + top.height - 1)
    // The grid was fitted before the timeline appeared under the panes; it must still fit after.
    const outline = (await gridOutline(page).boundingBox())!
    expect(outline.y).toBeGreaterThanOrEqual(top.y)
    expect(outline.y + outline.height).toBeLessThanOrEqual(top.y + top.height)

    await page.getByRole('button', { name: 'Stop', exact: true }).click()
    await expect(runStatus(page)).toHaveText('Stopped')
  })
})
