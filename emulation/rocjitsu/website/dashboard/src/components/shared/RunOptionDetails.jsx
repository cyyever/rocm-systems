import { Box, ListItemText } from '@mui/material';
import { commitTimestampFor } from '../../data/runOrdering';
import { shortSha } from '../../utils/formatters';
import { formatRunTime } from './runOptionPresentation';

export default function RunOptionDetails({ run, result }) {
  return <ListItemText
    primary={`Test run · ${formatRunTime(run.timestamp)}`}
    secondary={<>
      <Box component="span" sx={{ fontFamily: 'monospace', fontWeight: 700 }}>{shortSha(run)}</Box>
      {` · Commit · ${formatRunTime(commitTimestampFor(run))}`}
      <Box component="span" sx={{ display: 'block' }}>{run.branch} · {(run.modes ?? []).join(' / ')} · {run.runId}</Box>
      {result && <Box component="span" sx={{ display: 'block' }}>{result}</Box>}
    </>}
    slotProps={{ primary: { variant: 'body2', fontWeight: 680 }, secondary: { component: 'div', variant: 'caption', sx: { mt: 0.2 } } }}
  />;
}
