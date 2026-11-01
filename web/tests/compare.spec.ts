import { expect, test, type Page } from '@playwright/test'

// The fixture store: a reference, a second seed of the same decoder, and a better decoder.
const REFERENCE = '20261030T204955Z'
const SAME_DECODER = '20261101T171838Z'
const BETTER = '20261102T090000Z'

async function open(page: Page, a: string, b: string) {
  await page.goto(`/?a=${a}&b=${b}`)
  await expect(page.getByRole('region', { name: 'Comparison' })).toBeVisible({ timeout: 30_000 })
}

function headline(page: Page) {
  return page.getByRole('region', { name: 'Comparison' }).getByRole('status')
}

test('picks two runs from the address and judges the second against the first', async ({ page }) => {
  await open(page, REFERENCE, BETTER)
  await expect(page.getByRole('combobox', { name: 'Reference' })).toHaveValue(/20261030T204955Z/)
  await expect(page.getByRole('combobox', { name: 'Judged' })).toHaveValue(/20261102T090000Z/)
  await expect(headline(page)).toHaveText(/lower on \d+ of 40 cells, within the intervals on the rest/)
  await expect(page.getByRole('row')).toHaveCount(41)
})

test('calls two seeds of the same decoder within the intervals', async ({ page }) => {
  await open(page, REFERENCE, SAME_DECODER)
  await expect(headline(page)).toHaveText(/Within the intervals on every one of 40 cells|within the intervals on the rest/)
  const apart = page.getByRole('checkbox', { name: 'Only the cells set apart' })
  const lower = await page.getByRole('cell', { name: 'lower' }).count()
  const higher = await page.getByRole('cell', { name: 'higher' }).count()
  expect(lower + higher).toBeLessThan(4)
  if (lower + higher === 0) await expect(apart).toBeDisabled()
})

test('swapping keeps each run its colour and rewrites the address', async ({ page }) => {
  await open(page, REFERENCE, BETTER)
  const colourOf = (picker: string) => page.locator(`label[for="${picker}"] .key`)
  await expect(colourOf('run-a')).toHaveAttribute('data-colour', '1')
  await expect(colourOf('run-b')).toHaveAttribute('data-colour', '2')
  await page.getByRole('button', { name: 'Swap the two runs' }).click()
  await expect(page).toHaveURL(`/?a=${BETTER}&b=${REFERENCE}`)
  await expect(colourOf('run-a')).toHaveAttribute('data-colour', '2')
  await expect(colourOf('run-b')).toHaveAttribute('data-colour', '1')
  await expect(headline(page)).toHaveText(/higher on \d+ of 40 cells/)
})

test('filters the table to the cells set apart', async ({ page }) => {
  await open(page, REFERENCE, BETTER)
  const rows = page.getByRole('row')
  const before = await rows.count()
  await page.getByRole('checkbox', { name: 'Only the cells set apart' }).check()
  const after = await rows.count()
  expect(after).toBeLessThan(before)
  await expect(page.getByRole('cell', { name: 'within' })).toHaveCount(0)
})

test('draws the curves once the chart module arrives', async ({ page }) => {
  await open(page, REFERENCE, BETTER)
  const figure = page.getByRole('img', { name: /Error-rate curves/ })
  await expect(figure.locator('svg')).toBeVisible()
  await expect(figure.locator('svg circle').first()).toBeVisible()
  await expect(page.getByText('intervals apart', { exact: true })).toBeVisible()
})

test('traces a run to its commit, image and parent, and follows the parent', async ({ page }) => {
  await open(page, SAME_DECODER, BETTER)
  const judged = page.getByRole('region', { name: 'Where each run came from' }).locator('article').nth(1)
  await expect(judged.getByRole('link', { name: '0d0eebc668db' })).toHaveAttribute(
    'href',
    /\/commit\/0d0eebc668dbcbf66e3eea1245a8d9937afc5af8$/,
  )
  await expect(judged.getByRole('link', { name: 'sweep' })).toHaveAttribute('href', /pkgs\/container/)
  await expect(judged.locator('.digest')).toHaveText(/^sha256:[0-9a-f]{64}$/)
  await judged.getByRole('button', { name: 'judge against it' }).click()
  await expect(page).toHaveURL(`/?a=${REFERENCE}&b=${BETTER}`)
})

test('is driven end to end by keyboard alone', async ({ page }) => {
  await open(page, REFERENCE, BETTER)
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Skip to the comparison' })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.locator('main')).toBeFocused()
  await page.getByRole('combobox', { name: 'Judged' }).focus()
  await page.keyboard.press('Shift+Tab')
  await expect(page.getByRole('button', { name: 'Swap the two runs' })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(`/?a=${BETTER}&b=${REFERENCE}`)
})

test('remembers a chosen theme across loads', async ({ page }) => {
  await open(page, REFERENCE, BETTER)
  await page.getByRole('radio', { name: 'Dark' }).check()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await page.getByRole('radio', { name: 'System' }).check()
  await expect(page.locator('html')).not.toHaveAttribute('data-theme', /./)
})

test('says so when a run named in the address is not in the snapshot', async ({ page }) => {
  await page.goto('/?a=gone&b=' + BETTER)
  await expect(page.getByRole('combobox', { name: 'Judged' })).toHaveValue(/20261102T090000Z/, { timeout: 30_000 })
  await expect(page.getByText('Choose a reference and a run to judge against it.')).toBeVisible()
})
