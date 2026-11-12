import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'fs';

// A made-up 5-line BOM covering each case the review flow handles. The backend is mocked with the response shape
// /convert returns, so these tests check the UI logic: auto-picking drop-ins, choosing, skipping, and the cart file.

const spec = (name: string, original: string, candidate: string, result: string) => ({ name, original, candidate, result });

function alternative(mpn: string, dkpn: string, verdict: string, overrides: Record<string, unknown> = {}) {
  return {
    mpn, manufacturer: 'Acme', description: '', dkpn, packaging: 'Cut Tape (CT)', stock: 5000, moq: 1,
    unit_price: 0.1, status: 'ok', orderable: true, source: 'DigiKey direct substitute', verdict,
    detail: verdict === 'drop_in' ? 'meets or beats every listed spec' : 'worse on Tolerance: ±0.1% vs ±0.05%',
    specs: [spec('Tolerance', '±1%', verdict === 'drop_in' ? '±1%' : '±5%', verdict === 'drop_in' ? 'same' : 'worse')],
    worse_count: verdict === 'drop_in' ? 0 : 1, review: verdict !== 'drop_in', url: 'https://www.digikey.com/x',
    photo: '', datasheet: '', ...overrides,
  };
}

function row(designator: string, name: string, qty: number, status: string, dkpn: string, note = '') {
  return {
    Designator: designator, Name: name, Qty: String(qty), dk_mpn: name, dk_manufacturer: 'Acme', dkpn,
    dk_packaging: dkpn ? 'Cut Tape (CT)' : '', dk_qty_avail: status === 'ok' ? 1000 : 0, dk_moq: 1,
    dk_unit_price: 0.5, qty_per_board: qty, order_qty: qty * 2, match_status: status, match_note: note,
    dk_search_url: 'https://www.digikey.com/search',
  };
}

const RESPONSE = {
  rows: [
    row('R1, R2', 'GOOD-PART', 2, 'ok', 'GOOD-CT-ND'),
    row('C1', 'GONE-CAP', 1, 'out_of_stock', 'GONE-CT-ND', 'need 2, DigiKey has 0'),
    row('Q1', 'GONE-FET', 1, 'out_of_stock', 'FET-CT-ND', 'need 2, DigiKey has 0'),
    row('FID1', 'Fiducial', 1, 'not_a_part', '', 'board feature, not purchasable'),
    row('U1', 'GONE-IC', 1, 'out_of_stock', 'IC-CT-ND', 'need 2, DigiKey has 0'),
  ],
  alternatives: [
    [],
    [alternative('CAP-DROPIN', 'CAPDROP-CT-ND', 'drop_in'), alternative('CAP-WORSE', 'CAPWORSE-CT-ND', 'worse')],
    [alternative('FET-CHECK', 'FETCHECK-CT-ND', 'check')],
    [],
    [],
  ],
  row_count: 5, mpn_column: 'Name', part_number_column: null, qty_column: 'Qty', designator_column: 'Designator',
  boards: 2, statuses: {}, api_calls: 0, api_rate_remaining: 1000, cards: [null, null, null, null, null],
};

async function convert(page: Page) {
  await page.route('**/auth/status', (route) => route.fulfill({ json: { configured: true, has_refresh_token: true } }));
  await page.route('**/convert', (route) => route.fulfill({ json: RESPONSE }));
  await page.goto('');
  await page.locator('input[type=file]').setInputFiles({
    name: 'board.csv', mimeType: 'text/csv', buffer: Buffer.from('Name,Qty\nGOOD-PART,2\n'),
  });
  await page.locator('#boards').fill('2');
  await page.getByRole('button', { name: 'Convert to DigiKey BOM' }).click();
  await expect(page.getByRole('heading', { name: 'DigiKey BOM for 2 boards' })).toBeVisible();
}

function section(page: Page, mpn: string) {
  return page.locator('section[id^="decide-"]').filter({ hasText: mpn });
}

test('drop-ins are auto-picked; everything else waits for a decision', async ({ page }) => {
  await convert(page);
  await expect(page.getByText('2 ready for the cart')).toBeVisible(); // GOOD-PART + auto-picked CAP-DROPIN
  await expect(page.getByText('2 undecided (not in cart)')).toBeVisible(); // GONE-FET (only "check"), GONE-IC (none)
  await expect(section(page, 'GONE-CAP').getByText('Using CAP-DROPIN (drop-in)')).toBeVisible();
  await expect(section(page, 'GONE-FET').getByText('Undecided: not in the cart yet')).toBeVisible();
  await expect(section(page, 'GONE-IC').getByText('No in-stock replacement found on DigiKey')).toBeVisible();
  await expect(page.getByRole('button', { name: 'DigiKey cart CSV (decide 2 lines first)' })).toBeDisabled();
});

test('pasted replacement is spec-checked and used; cart unlocks once every line is decided', async ({ page }) => {
  let lookupBody: Record<string, unknown> = {};
  await page.route('**/lookup', (route) => {
    lookupBody = route.request().postDataJSON();
    route.fulfill({ json: alternative('IC-MINE', 'ICMINE-CT-ND', 'check', { source: 'manual' }) });
  });
  await convert(page);
  const ic = section(page, 'GONE-IC');
  await ic.getByLabel('Replacement part').fill('https://www.digikey.com/en/products/detail/acme/IC-MINE/123');
  await ic.getByRole('button', { name: 'Check part' }).click();
  await expect(ic.getByText('Using IC-MINE (your choice)')).toBeVisible();
  await expect(ic.getByText('your pick', { exact: true })).toBeVisible();
  expect(lookupBody).toMatchObject({ need: 2, query: 'https://www.digikey.com/en/products/detail/acme/IC-MINE/123' });

  await expect(page.getByRole('button', { name: 'DigiKey cart CSV (decide 1 line first)' })).toBeDisabled();
  const fet = section(page, 'GONE-FET');
  await fet.getByRole('button', { name: 'Skip this line' }).click();
  await expect(page.getByText('Skipped by you')).toBeVisible();

  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'DigiKey cart CSV (3)' }).click();
  const csv = readFileSync(await (await download).path(), 'utf-8');
  expect(csv).toContain('ICMINE-CT-ND,IC-MINE,2,U1');
});

test('standard parts come from ELL stock and can be ordered anyway', async ({ page }) => {
  const response = {
    ...RESPONSE,
    rows: [...RESPONSE.rows, row('C9, C10', 'C0603C104K5RACTU', 2, 'lab_stock', '', 'on the standard parts sheet, pull from ELL stock')],
    alternatives: [...RESPONSE.alternatives, []],
    cards: [...RESPONSE.cards, null],
    standard_parts: { enabled: true, count: 38, error: null, url: 'https://docs.google.com/spreadsheets/d/x/edit', manual_count: 0 },
  };
  await page.route('**/auth/status', (route) => route.fulfill({ json: { configured: true, has_refresh_token: true } }));
  await page.route('**/convert', (route) => route.fulfill({ json: response }));
  await page.route('**/lookup', (route) =>
    route.fulfill({ json: alternative('C0603C104K5RACTU', '399-C0603C104K5RACTUCT-ND', 'unverified') }),
  );
  await page.goto('');
  await page.locator('input[type=file]').setInputFiles({ name: 'b.csv', mimeType: 'text/csv', buffer: Buffer.from('Name\nX\n') });
  await page.locator('#boards').fill('2');
  await page.getByRole('button', { name: 'Convert to DigiKey BOM' }).click();

  await expect(page.getByText('1 from ELL stock')).toBeVisible();
  await expect(page.getByText('38 standard parts')).toBeVisible();
  // Lab-stock lines don't block the cart: only the two real undecided lines do.
  await expect(page.getByRole('button', { name: 'DigiKey cart CSV (decide 2 lines first)' })).toBeDisabled();

  const lab = page.getByTestId('lab-5');
  await lab.getByRole('button', { name: 'Order from DigiKey anyway' }).click();
  await expect(lab.getByText('Ordering 399-C0603C104K5RACTUCT-ND from DigiKey')).toBeVisible();
  await expect(page.getByText('3 ready for the cart')).toBeVisible();
  await lab.getByRole('button', { name: 'Use ELL stock instead' }).click();
  await expect(page.getByText('2 ready for the cart')).toBeVisible();
});

test('ELL-stock settings are sent with the conversion and remembered', async ({ page }) => {
  let body = '';
  await page.route('**/auth/status', (route) => route.fulfill({ json: { configured: true, has_refresh_token: true } }));
  await page.route('**/convert', (route) => {
    body = route.request().postData() ?? '';
    route.fulfill({ json: RESPONSE });
  });
  await page.goto('');
  await page.getByLabel(/standard parts sheet/).uncheck();
  await page.getByLabel(/Also in the ELL/).fill('GRM188R71H104KA93D\nPMEG2010ER,115');
  await expect(page.getByText(/Also in the ELL \(2\)/)).toBeVisible();
  await page.locator('input[type=file]').setInputFiles({ name: 'b.csv', mimeType: 'text/csv', buffer: Buffer.from('Name\nX\n') });
  await page.getByRole('button', { name: 'Convert to DigiKey BOM' }).click();
  await expect(page.getByRole('heading', { name: /DigiKey BOM for/ })).toBeVisible();
  expect(body).toMatch(/name="use_standard_sheet"\r\n\r\nfalse/);
  expect(body).toMatch(/GRM188R71H104KA93D\r?\nPMEG2010ER,115/); // the browser sends CRLF; the backend splits either

  await page.reload();
  await expect(page.getByLabel(/Also in the ELL/)).toHaveValue('GRM188R71H104KA93D\nPMEG2010ER,115');
  await expect(page.getByLabel(/standard parts sheet/)).not.toBeChecked();
});

test('lookup errors are shown on the line', async ({ page }) => {
  await page.route('**/lookup', (route) =>
    route.fulfill({ status: 404, json: { detail: 'Only DigiKey parts can go in the DigiKey cart.' } }),
  );
  await convert(page);
  const ic = section(page, 'GONE-IC');
  await ic.getByLabel('Replacement part').fill('https://www.mouser.com/x');
  await ic.getByRole('button', { name: 'Check part' }).click();
  await expect(ic.getByText('Only DigiKey parts can go in the DigiKey cart.')).toBeVisible();
  await expect(ic.getByText('Undecided: not in the cart yet')).toBeVisible();
});

test('choosing, skipping and the cart CSV', async ({ page }) => {
  await convert(page);
  await section(page, 'GONE-FET').getByRole('button', { name: 'Use this' }).click();
  await section(page, 'GONE-IC').getByRole('button', { name: 'Skip this line' }).click();
  await expect(page.getByText('3 ready for the cart')).toBeVisible();
  await expect(page.getByText('2 skipped')).toBeVisible(); // fiducial + GONE-IC
  await expect(page.getByText(/undecided \(not in cart\)/)).toHaveCount(0);

  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: /DigiKey cart CSV/ }).click();
  const csv = readFileSync(await (await download).path(), 'utf-8').trim().split(/\r?\n/);
  expect(csv).toEqual([
    'Digi-Key Part Number,Manufacturer Part Number,Quantity,Reference Designator',
    'GOOD-CT-ND,GOOD-PART,4,"R1, R2"',
    'CAPDROP-CT-ND,CAP-DROPIN,2,C1',
    'FETCHECK-CT-ND,FET-CHECK,2,Q1',
  ]);
});


test('quota exhausted shows when to try again', async ({ page }) => {
  await page.route('**/auth/status', (route) => route.fulfill({ json: { configured: true, has_refresh_token: true } }));
  await page.route('**/convert', (route) =>
    route.fulfill({ status: 429, json: { detail: 'DigiKey API limit reached for today. Try again in about 3 h 20 min.' } }),
  );
  await page.goto('');
  await page.locator('input[type=file]').setInputFiles({ name: 'b.csv', mimeType: 'text/csv', buffer: Buffer.from('Name\nX\n') });
  await page.getByRole('button', { name: 'Convert to DigiKey BOM' }).click();
  await expect(page.getByText('DigiKey API limit reached for today. Try again in about 3 h 20 min.')).toBeVisible();
});

