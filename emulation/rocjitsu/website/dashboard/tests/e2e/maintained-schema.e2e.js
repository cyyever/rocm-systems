import { expect, test } from '@playwright/test';
import { createMaintainedPublication } from '../fixtures/maintainedDataset.js';
import { downloadSource, inspectResult, installPublication, openDashboard, ready } from './helpers/dashboard.js';

test('typed definitions render in details and remain intact in filtered JSON export and reload', async ({ page }) => {
  const publication = createMaintainedPublication();
  const problem = { shape: [16, 16], options: { transpose: false, note: null }, note: null, literal: '[16,16]' };
  for (const catalog of Object.values(publication.catalogs)) {
    catalog.benchmark_definitions.a.problem = structuredClone(problem);
  }
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
  await installPublication(page, { publication });
  await openDashboard(page, '/?view=benchmarks&targets=gfx1250&modes=single');
  const details = await inspectResult(page, 'Fictional GEMM', 'fictional-develop-23');
  await expect(details.getByText('[16,16]', { exact: true })).toHaveCount(2);
  await expect(details.getByText('{"transpose":false,"note":null}', { exact: true })).toBeVisible();
  await expect(details.getByText('null', { exact: true })).toBeVisible();
  await details.getByRole('button', { name: 'Close details', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true }).click();
  await ready(page);
  expect(await downloadSource(page)).toEqual(publication);
  await page.reload();
  await ready(page);
  expect(new URL(page.url()).searchParams.getAll('modes')).toEqual(['single']);
  expect(await downloadSource(page)).toEqual(publication);
  expect(errors).toEqual([]);
});
