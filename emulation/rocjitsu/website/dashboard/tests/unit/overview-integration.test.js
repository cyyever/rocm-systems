import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, test, vi } from 'vitest';
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
  for (const title of ['Latest duration', 'Relative speedup', 'Compared workloads', 'Latest results']) expect(html).toContain(title);
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
