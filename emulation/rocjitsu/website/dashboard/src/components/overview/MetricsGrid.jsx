import { Box, Paper, Typography } from '@mui/material';
import TimerRoundedIcon from '@mui/icons-material/TimerRounded';
import SpeedRoundedIcon from '@mui/icons-material/SpeedRounded';
import FactCheckRoundedIcon from '@mui/icons-material/FactCheckRounded';
import ChecklistRoundedIcon from '@mui/icons-material/ChecklistRounded';
import { monoFont } from '../../theme/tokens';
import { formatDuration } from '../../utils/formatters';

function Metric({ label, rows, valueFor, caption, icon: Icon }) {
  return <Box data-testid={`metric-card-${label.toLowerCase().replaceAll(' ', '-')}`} data-tone="neutral" sx={{ p: 2, minWidth: 0 }}>
    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, mb: 1 }}>
      <Typography variant="overline" sx={{ color: 'text.secondary', fontSize: 11 }}>{label}</Typography>
      <Icon aria-hidden="true" sx={{ color: 'text.secondary', fontSize: 18 }} />
    </Box>
    {!rows.length ? <Typography color="text.secondary">No configurations selected</Typography> : rows.map((row) => <Box key={row.key} data-configuration={row.key} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 1, py: 0.3 }}>
      <Typography variant="caption" sx={{ overflowWrap: 'anywhere' }}>{row.target} {row.mode}</Typography>
      <Typography title={row.latest.reason ?? undefined} sx={{ fontFamily: monoFont, fontSize: rows.length === 1 ? 24 : 13, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{!row.cohortIds.length ? 'No shared workloads' : valueFor(row)}</Typography>
    </Box>)}
    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1, fontSize: 10 }}>{caption}</Typography>
  </Box>;
}

export default function MetricsGrid({ projection }) {
  const rows = projection.rows;
  return <Paper variant="outlined" data-testid="metric-strip" sx={{ borderRadius: 1, display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(2,minmax(0,1fr))', md: 'repeat(4,minmax(0,1fr))' }, overflow: 'hidden', '& > div': { borderRight: { md: 1 }, borderBottom: { xs: 1, md: 0 }, borderColor: 'divider' }, '& > div:last-child': { border: 0 } }}>
    <Metric label="Latest duration" icon={TimerRoundedIcon} rows={rows} valueFor={(r) => r.latest.durationSeconds == null ? 'Unavailable' : formatDuration(r.latest.durationSeconds)} caption={projection.endpointLabel} />
    <Metric label="Relative speedup" icon={SpeedRoundedIcon} rows={rows} valueFor={(r) => r.latest.speedup == null ? 'Unavailable' : `${r.latest.speedup.toFixed(2)}×`} caption="First valid reference / latest · higher is faster" />
    <Metric label="Latest results" icon={ChecklistRoundedIcon} rows={rows} valueFor={(r) => `${r.latest.completed}/${r.latest.required}`} caption="Succeeded / required workloads" />
    <Metric label="Valid data points" icon={FactCheckRoundedIcon} rows={rows} valueFor={(r) => r.points.filter((point) => Number.isFinite(point.speedup)).length} caption="Plotted points in selected range" />
  </Paper>;
}
