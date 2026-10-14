import { useState } from 'react';
import { Box, MenuItem, Select, Stack, Typography } from '@mui/material';
import SectionCard from '../shared/SectionCard';
import CategoryTag from '../shared/CategoryTag';
import { monoFont } from '../../theme/tokens';
import { formatPercent, shortSha } from '../../utils/formatters';
import { changeTone, classifyDurationChange } from '../../utils/performance';

export default function LargestChanges({ projection }) {
  const [selection, setSelection] = useState(null);
  const row = projection.rows.find(({ key }) => key === selection) ?? projection.rows[0];
  const baseline = row?.reference;
  const candidate = row?.latest;
  const changes = candidate?.durationSeconds > 0 && baseline?.durationSeconds > 0 ? candidate.results.flatMap(({ id, result }) => {
    const reference = baseline.results.find((item) => item.id === id)?.result;
    const delta = reference?.durationSeconds > 0 ? (result.durationSeconds - reference.durationSeconds) / reference.durationSeconds * 100 : null;
    return Number.isFinite(delta) ? [{ id, result, delta }] : [];
  }).sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta) || a.id.localeCompare(b.id)).slice(0, 6) : [];
  const maximum = Math.max(...changes.map(({ delta }) => Math.abs(delta)), 0);
  return <SectionCard title="Largest Changes" subtitle="Duration change (%) · lower is faster" sx={{ height: '100%', minWidth: 0 }} contentSx={{ p: 2 }} data-testid="largest-changes">
    <Select size="small" value={row?.key ?? ''} displayEmpty inputProps={{ 'aria-label': 'Largest Changes configuration' }} onChange={(e) => setSelection(e.target.value)} sx={{ mb: 1, width: '100%', fontSize: 12 }}>
      {!projection.rows.length && <MenuItem value="">No configurations selected</MenuItem>}
      {projection.rows.map((r) => <MenuItem key={r.key} value={r.key}>{r.target} {r.mode}</MenuItem>)}
    </Select>
    {!changes.length ? <Typography color="text.secondary" sx={{ py: 4, fontSize: 12 }}>No comparable results: {row?.cohortIds.length ? candidate?.reason ?? 'no valid reference' : 'No shared workloads'}.</Typography> : changes.map(({ id, result, delta }) => {
      const state = classifyDurationChange(delta, 3);
      const tone = changeTone(state);
      return <Box key={id} data-change-state={state} sx={{ py: 1.1 }}>
        <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', gap: 1 }}>
          <Box sx={{ minWidth: 0 }}><Typography sx={{ fontWeight: 600, overflowWrap: 'anywhere', fontSize: 12 }}>{result.name}</Typography>
            <Stack direction="row" sx={{ mt: 0.4, gap: 0.5, flexWrap: 'wrap' }}><CategoryTag kind="target" label={row.target} /><CategoryTag label={result.suite} /><CategoryTag kind="mode" label={row.mode} /></Stack>
          </Box>
          <Typography title={`Latest ${shortSha(candidate.run)} vs reference ${shortSha(baseline.run)}`} sx={{ flexShrink: 0, fontFamily: monoFont, fontSize: 15, color: tone === 'neutral' ? 'text.secondary' : `${tone}.main` }}>{formatPercent(delta)}</Typography>
        </Stack>
        <Box aria-hidden="true" sx={{ mt: 1, height: 3, bgcolor: 'divider', borderRadius: 1 }}><Box data-testid="change-magnitude-bar" sx={{ height: '100%', width: `${maximum ? Math.abs(delta) / maximum * 100 : 0}%`, bgcolor: tone === 'neutral' ? 'text.disabled' : `${tone}.main`, borderRadius: 1 }} /></Box>
      </Box>;
    })}
  </SectionCard>;
}
