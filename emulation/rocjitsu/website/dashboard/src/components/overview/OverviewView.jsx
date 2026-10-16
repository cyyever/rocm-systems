import { useMemo } from 'react';
import { Box, Stack } from '@mui/material';
import { sortRunsByCommit } from '../../data/runOrdering';
import { formatShortDate } from '../../utils/formatters';
import DurationHistory from './DurationHistory';
import LargestChanges from './LargestChanges';
import MetricsGrid from './MetricsGrid';
import RecentRuns from './RecentRuns';

export default function OverviewView({ viewModel, data, state, onOpenBenchmarks }) {
  const catalogs = useMemo(() => {
    const latest = new Map();
    for (const run of sortRunsByCommit(data.runs)) {
      const catalog = data.catalogs?.[run.testCatalog];
      if (catalog) latest.set(catalog.id, { catalog, timestamp: run.commitTimestamp });
    }
    return [...latest.values()].sort((a, b) => b.timestamp.localeCompare(a.timestamp) || a.catalog.id.localeCompare(b.catalog.id))
      .map((entry) => ({ ...entry, label: `${entry.catalog.id} · ${formatShortDate(entry.timestamp)}` }));
  }, [data]);
  return <Stack sx={{ gap: 1.75, minWidth: 0 }}>
    <MetricsGrid projection={viewModel} />
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'minmax(0,1.7fr) minmax(0,1fr)' }, gap: 1.75, alignItems: 'stretch' }}>
      <DurationHistory projection={viewModel} catalogs={catalogs} onRangeChange={state.setHistoryRange} onCatalogChange={state.setOverviewCatalogId} onOpenBenchmarks={onOpenBenchmarks} />
      <LargestChanges projection={viewModel} catalogs={catalogs} />
    </Box>
    <RecentRuns data={data} filters={state.filters} />
  </Stack>;
}
