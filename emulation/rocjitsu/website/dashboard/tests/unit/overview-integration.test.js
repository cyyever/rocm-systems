import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, test, vi } from 'vitest';
import LargestChanges from '../../src/components/overview/LargestChanges.jsx';
import MetricsGrid from '../../src/components/overview/MetricsGrid.jsx';
import DurationHistory from '../../src/components/overview/DurationHistory.jsx';
import { readDashboardRoute, buildDashboardUrl } from '../../src/hooks/useDashboardState.js';

const capture = vi.hoisted(() => ({ props: null }));
vi.mock('../../src/components/shared/Chart.jsx', () => ({ default: (props) => { capture.props = props; return createElement('div'); } }));
const run = { runId: 'attempt', timestamp: '2026-01-01T12:00:00Z', provenance: { rocjitsuCommitSha: 'abc' } };
const point = { run, runId: 'attempt', durationSeconds: 12, speedup: 1, required: 2, completed: 2, reason: null };
const projection = { rows: [{ key: 'gfx950/single', target: 'gfx950', mode: 'single', cohortIds: ['a', 'b'], comparedWorkloads: 2, reference: point, latest: point, points: [point, { ...point, run: null, speedup: null, durationSeconds: null }] }],
  slots: [{ run, x: 0 }, { run: null, x: 1 }], range: '1M', dayKeys: ['2026-01-01', '2026-01-02'], axisMax: 1, endpointLabel: 'Latest selected run' };

test('cards consume per-configuration endpoints and show only succeeded/required', () => {
  const html = renderToStaticMarkup(createElement(MetricsGrid, { projection }));
  const cards = [...html.matchAll(/data-testid="metric-card-([^"]+)"/g)].map((match) => match[1]);
  expect(cards).toEqual(['latest-duration', 'relative-speedup', 'latest-results', 'valid-data-points']);
  expect(html).not.toContain('Compared workloads');
  expect(html).toContain('2/2');
  expect(html).toContain('1.00×');
  expect(html).not.toContain('Run health');
});
test('relative chart has only configuration series, no gap bridges, dots or fill, and gap tooltip is empty', () => {
  renderToStaticMarkup(createElement(DurationHistory, { projection, catalogs: [], onRangeChange() {}, onCatalogChange() {} }));
  const option = capture.props.option;
  expect(option.series).toHaveLength(1);
  expect(option.series[0]).toMatchObject({ connectNulls: false, showSymbol: false, symbol: 'none' });
  expect(option.series[0].areaStyle).toBeUndefined();
  expect(option.tooltip.formatter([{ dataIndex: 1 }])).toBe('');
  expect(option.tooltip.formatter([{ dataIndex: 0 }])).toContain('attempt');
});
test('Largest Changes ranks one flat six-entry list across configurations with original item labels', () => {
  const row = (target, deltas) => ({ ...projection.rows[0], key: `${target}/single`, target,
    reference: { ...point, results: deltas.map((_, i) => ({ id: `work-${i}`, result: { durationSeconds: 100 } })) },
    latest: { ...point, results: deltas.map((delta, i) => ({ id: `work-${i}`, result: { name: `${target}-${i}`, suite: 'Triton', durationSeconds: 100 + delta } })) } });
  const html = renderToStaticMarkup(createElement(LargestChanges, { projection: { ...projection, catalogId: 'current', rows: [row('gfx950', [10, 30, 50, 70]), row('gfx1250', [-20, -40, -60, -80])] } }));
  expect((html.match(/data-change-state=/g) ?? [])).toHaveLength(6);
  const names = ['gfx1250-3', 'gfx950-3', 'gfx1250-2', 'gfx950-2', 'gfx1250-1', 'gfx950-1'];
  expect(names.map((name) => html.indexOf(`>${name}<`))).toEqual([...names.map((name) => html.indexOf(`>${name}<`))].sort((a, b) => a - b));
  expect(html).not.toContain('>gfx950-0<');
  expect(html).not.toContain('data-configuration-group');
  expect(html).not.toContain('combobox');
  for (const label of ['gfx950', 'gfx1250', 'Triton', 'single']) expect(html).toContain(`>${label}<`);
});

test('Largest Changes applies displayed-catalog shared membership before ranking and limit', () => {
  const catalogs = [
    { catalog: { id: 'old', configurations: { 'gfx950/single': ['a', 'b', 'retired'] } } },
    { catalog: { id: 'current', configurations: { 'gfx950/single': ['a', 'b', 'added'] } } },
  ];
  const ids = ['a', 'b', 'added'];
  const row = { ...projection.rows[0], cohortIds: ids,
    reference: { ...point, results: ids.map((id) => ({ id, result: { durationSeconds: 100 } })) },
    latest: { ...point, results: ids.map((id, i) => ({ id, result: { name: id, suite: 'Triton', durationSeconds: i === 2 ? 1000 : 110 + i } })) } };
  const render = (catalogId) => renderToStaticMarkup(createElement(LargestChanges, { catalogs, projection: { ...projection, catalogId, rows: [row] } }));
  const shared = render(null);
  expect((shared.match(/data-change-state=/g) ?? [])).toHaveLength(2);
  expect(shared).not.toContain('data-workload="added"');
  expect(render('current')).toContain('data-workload="added"');
});

test('Largest Changes excludes invalid endpoints and preserves empty/unavailable reasons', () => {
  const unavailable = { ...projection.rows[0], latest: { ...point, reason: 'failed', durationSeconds: null } };
  const render = (rows) => renderToStaticMarkup(createElement(LargestChanges, { projection: { ...projection, catalogId: 'current', rows } }));
  expect(render([unavailable])).toContain('failed');
  expect(render([unavailable])).not.toContain('data-change-state');
  expect(render([])).toContain('No configurations selected');
});

test('catalog routing preserves unrelated query/hash and explicit selections', () => {
  expect(readDashboardRoute('https://example.test/').historyRange).toBe('1W');
  const route = readDashboardRoute('https://example.test/?catalog=cat-a&range=1M&targets=&view=overview&keep=yes#anchor');
  expect(route.overviewCatalogId).toBe('cat-a');
  expect(route.preferences.targets).toEqual([]);
  const url = buildDashboardUrl('https://example.test/?keep=yes#anchor', route);
  expect(new URL(url).searchParams.get('catalog')).toBe('cat-a');
  expect(new URL(url).searchParams.get('keep')).toBe('yes');
  expect(new URL(url).hash).toBe('#anchor');
});
