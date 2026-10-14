import { memo, useEffect, useId, useMemo, useRef, useState } from 'react';
import { Box, Link, MenuItem, Select, Stack, ToggleButton, ToggleButtonGroup, Typography, useTheme } from '@mui/material';
import Chart from '../shared/Chart';
import SectionCard from '../shared/SectionCard';
import CatalogWorkloads from './CatalogWorkloads';
import { escapeHtml, formatDuration, formatFullDate, formatShortDate } from '../../utils/formatters';
import { targetColor } from '../../utils/chartColors';
import { historyRanges } from '../../config/historyRanges';
import { visuallyHiddenStyles } from '../../theme/styles';
import { trendKeyIndex, nearestTrendIndex } from './overviewPresentation';

const StableChart = memo(Chart);
const colorFor = (row, index) => row.mode === 'default' ? ({ gfx1250: '#14826F', gfx950: '#7450B8' }[row.target] ?? targetColor(row.target, index + 2)) : targetColor(row.target, index);

export default function DurationHistory({ projection, catalogs, onRangeChange, onCatalogChange, onOpenBenchmarks }) {
  const theme = useTheme();
  const helpId = useId();
  const catalogLabelId = useId();
  const chartRef = useRef(null);
  const guideRef = useRef(null);
  const focusRef = useRef(null);
  const pointerSource = useRef('mouse');
  const [inspection, setInspection] = useState(null);
  const inspected = inspection?.projection === projection ? inspection.index : null;
  const eligible = projection.slots.flatMap((slot, index) => slot.run && projection.rows.some((r) => Number.isFinite(r.points[index]?.speedup)) ? [index] : []);
  const colors = projection.rows.map(colorFor);
  const clear = () => {
    const chart = chartRef.current;
    if (chart && !chart.isDisposed()) chart.dispatchAction({ type: 'hideTip' });
    if (guideRef.current) guideRef.current.style.display = 'none';
    if (focusRef.current) focusRef.current.style.display = 'none';
  };
  useEffect(() => {
    // Projection changes invalidate imperative hover DOM as well as logical inspection.
    if (guideRef.current) guideRef.current.style.display = 'none';
    if (focusRef.current) { focusRef.current.style.display = 'none'; focusRef.current.innerHTML = ''; }
    const chart = chartRef.current;
    if (chart && !chart.isDisposed()) chart.dispatchAction({ type: 'hideTip' });
  }, [projection]);
  const inspect = (index) => {
    const chart = chartRef.current;
    if (index == null || !chart || chart.isDisposed()) { clear(); return; }
    const hits = projection.rows.flatMap((r, si) => Number.isFinite(r.points[index]?.speedup) ? [si] : []);
    if (!hits.length) { clear(); return; }
    setInspection((current) => current?.projection === projection && current.index === index ? current : { projection, index });
    chart.dispatchAction({ type: 'showTip', seriesIndex: hits[0], dataIndex: index });
    const x = chart.convertToPixel({ xAxisIndex: 0 }, projection.slots[index].x);
    Object.assign(guideRef.current.style, { display: 'block', left: `${x}px` });
    // Temporary emphasis is a small segment overlay, not persistent point dots.
    focusRef.current.innerHTML = hits.map((si) => {
      const row = projection.rows[si];
      const center = chart.convertToPixel({ seriesIndex: si }, [projection.slots[index].x, row.points[index].speedup]);
      const paths = [index - 1, index + 1].filter((i) => Number.isFinite(row.points[i]?.speedup)).map((i) => {
        const other = chart.convertToPixel({ seriesIndex: si }, [projection.slots[i].x, row.points[i].speedup]);
        const fraction = Math.min(1, 8 / Math.max(1, Math.abs(other[0] - center[0])));
        return `M${center[0]},${center[1]} L${center[0] + (other[0] - center[0]) * fraction},${center[1] + (other[1] - center[1]) * fraction}`;
      }).join(' ');
      return `<path d="${paths}" fill="none" stroke="${colors[si]}" stroke-width="5"/>`;
    }).join('');
    focusRef.current.style.display = 'block';
  };
  const option = useMemo(() => ({
    animation: false,
    grid: { left: 50, right: 14, top: 26, bottom: 40 },
    tooltip: { trigger: 'axis', triggerOn: 'none', axisPointer: { type: 'none' }, transitionDuration: 0, confine: true, textStyle: { fontSize: 11 },
      formatter: (parameters) => {
        const index = (Array.isArray(parameters) ? parameters[0] : parameters)?.dataIndex;
        const slot = projection.slots[index];
        const valid = projection.rows.filter((row) => Number.isFinite(row.points[index]?.speedup));
        if (!slot?.run || !valid.length) return '';
        return `<b>Run time: ${escapeHtml(formatFullDate(slot.run.timestamp))}</b><br/>Attempt: ${escapeHtml(slot.run.runId)}<br/>${escapeHtml(slot.run.provenance.rocjitsuCommitSha.slice(0, 8))}<br/>` + valid.map((row) => {
          const point = row.points[index];
          return `${escapeHtml(row.target)} ${escapeHtml(row.mode)} · <b>${point.speedup.toFixed(3)}×</b> · ${escapeHtml(formatDuration(point.durationSeconds))} (${point.durationSeconds}s)<br/>Reference: ${escapeHtml(row.reference.runId)} · ${row.reference.durationSeconds}s`;
        }).join('<br/>');
      } },
    xAxis: { type: 'value', min: 0, max: Math.max(1, projection.axisMax), axisTick: { show: false }, splitLine: { show: false },
      axisLabel: { color: theme.palette.text.secondary, hideOverlap: true, formatter: (x) => {
        const day = projection.dayKeys[Math.round(x)];
        return day ? formatShortDate(`${day}T12:00:00Z`) : '';
      } }, axisLine: { lineStyle: { color: theme.palette.divider } } },
    yAxis: { type: 'value', name: 'Relative speedup (×)', scale: true, min: (extent) => Math.min(0.99, extent.min - 0.01), max: (extent) => Math.max(1.01, extent.max + 0.01),
      nameTextStyle: { align: 'left', color: theme.palette.text.secondary }, axisLabel: { formatter: (v) => `${v.toFixed(2)}×`, color: theme.palette.text.secondary }, splitLine: { lineStyle: { color: theme.palette.divider } } },
    series: projection.rows.map((row, index) => ({ name: `${row.target} ${row.mode}`, type: 'line',
      data: row.points.map((point, i) => [projection.slots[i].x, point.speedup]), connectNulls: false,
      showSymbol: false, symbol: 'none', emphasis: { disabled: true }, lineStyle: { width: 2.5, color: colorFor(row, index) },
      ...(index === 0 ? { markLine: { silent: true, symbol: 'none', label: { show: false }, lineStyle: { type: 'dashed', color: theme.palette.text.disabled }, data: [{ yAxis: 1 }] } } : {}) })),
  }), [projection, theme]);
  const onReady = useMemo(() => (chart) => { chartRef.current = chart; }, []);
  const pointer = (event) => {
    const chart = chartRef.current;
    if (!chart || chart.isDisposed()) return;
    const rect = chart.getDom().getBoundingClientRect();
    const pixel = [(event.clientX - rect.left) * chart.getWidth() / rect.width, (event.clientY - rect.top) * chart.getHeight() / rect.height];
    if (!chart.containPixel('grid', pixel)) { clear(); return; }
    inspect(nearestTrendIndex(projection, chart.convertFromPixel('grid', pixel)[0]));
  };
  return <SectionCard data-testid="performance-trend" title="Performance Trend" subtitle="Relative speedup · higher is faster · develop only" sx={{ height: '100%', minWidth: 0 }} contentSx={{ p: 2 }} action={<Box sx={{ maxWidth: '100%', overflowX: 'auto' }}><ToggleButtonGroup exclusive size="small" value={projection.range} onChange={(_, next) => next && onRangeChange(next)} aria-label="History timeframe">{historyRanges.map(({ id, label }) => <ToggleButton key={id} value={id} aria-label={label} sx={{ px: 1, minHeight: { xs: 44, sm: 36 } }}>{id}</ToggleButton>)}</ToggleButtonGroup></Box>}>
    <Stack direction="row" sx={{ alignItems: 'center', flexWrap: 'wrap', gap: 1, mb: 1 }}>
      <Typography id={catalogLabelId} variant="caption" color="text.secondary">Catalog</Typography>
      <Select labelId={catalogLabelId} value={projection.catalogId ?? ''} onChange={(e) => { clear(); onCatalogChange(e.target.value || null); }} size="small" displayEmpty sx={{ minWidth: 170, maxWidth: '100%', fontSize: 12 }}>
        <MenuItem value="">Shared benchmarks</MenuItem>{projection.catalogId && !catalogs.some(({ catalog }) => catalog.id === projection.catalogId) && <MenuItem value={projection.catalogId}>Unavailable catalog</MenuItem>}
        {catalogs.map(({ catalog, label }) => <MenuItem key={catalog.id} value={catalog.id}>{label}</MenuItem>)}
      </Select>
      <Typography variant="caption" color="text.secondary">1.00× = each configuration’s first valid positive point in range.</Typography>
    </Stack>
    <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 2, mb: 1 }}>{projection.rows.map((row, index) => <Typography key={row.key} variant="caption"><Box component="span" sx={{ color: colors[index], mr: 0.75 }}>{row.mode === 'single' ? '●' : '◆'}</Box>{row.target} {row.mode}</Typography>)}</Stack>
    {!eligible.length ? <Box data-testid="speedup-empty-state" role="status" sx={{ height: 280, display: 'grid', placeItems: 'center', textAlign: 'center', px: 2 }}><Typography variant="body2" color="text.secondary">Relative speedup unavailable: no positive valid reference in the selected range.</Typography></Box> : <Box data-testid="performance-trend-chart" tabIndex={0} role="group" aria-label="Inspect performance trend" aria-describedby={helpId}
      onKeyDown={(e) => { if (!['ArrowLeft', 'ArrowRight', 'Home', 'End', 'Escape'].includes(e.key)) return; e.preventDefault(); pointerSource.current = 'keyboard'; inspect(trendKeyIndex(eligible, inspected, e.key)); if (e.key === 'Escape') setInspection(null); }}
      onPointerMove={(e) => { if (e.pointerType === 'mouse' || e.pointerType === 'pen') { pointerSource.current = e.pointerType; pointer(e); } }}
      onPointerDown={(e) => { pointerSource.current = e.pointerType; pointer(e); }}
      onPointerLeave={() => { if (['mouse', 'pen'].includes(pointerSource.current)) clear(); }}
      sx={{ position: 'relative', mt: 1, outlineOffset: 2, '&:focus-visible': { outline: '2px solid', outlineColor: 'primary.main' } }}>
      <Box ref={guideRef} data-testid="point-hover-guide" aria-hidden="true" sx={{ display: 'none', pointerEvents: 'none', position: 'absolute', top: 26, bottom: 40, borderLeft: '1px dotted', borderColor: 'text.secondary', zIndex: 1 }} />
      <Box component="svg" ref={focusRef} data-testid="hover-line-focus" aria-hidden="true" sx={{ position: 'absolute', inset: 0, width: '100%', height: 280, display: 'none', pointerEvents: 'none', zIndex: 2 }} />
      <StableChart option={option} height={280} ariaLabel="Relative speedup by configuration; gaps unconnected" lazyUpdate={false} onReady={onReady} />
    </Box>}
    {inspected != null && <Typography role="status" aria-live="polite" sx={visuallyHiddenStyles}>{projection.slots[inspected]?.run?.runId} · {projection.rows.filter((r) => Number.isFinite(r.points[inspected]?.speedup)).map((r) => `${r.target} ${r.mode}: ${r.points[inspected].speedup.toFixed(3)} times`).join(' · ')}</Typography>}
    <Typography id={helpId} variant="caption" color="text.secondary" sx={{ fontSize: 10 }}>Arrow keys inspect runs · Home/End first/last · Escape clears · Date (UTC)</Typography>
    <CatalogWorkloads catalogs={catalogs} projection={projection} />
    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>{projection.endpointLabel}{projection.weeklyEligibility ? ' · provisional: selected required workloads succeed' : ''}. Original per-benchmark results: <Link component="button" type="button" onClick={onOpenBenchmarks} sx={{ font: 'inherit' }}>Benchmarks</Link>.</Typography>
  </SectionCard>;
}
