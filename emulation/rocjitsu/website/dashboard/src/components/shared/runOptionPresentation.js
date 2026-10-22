import { shortSha } from '../../utils/formatters';

const runTimeFormatter = new Intl.DateTimeFormat(undefined, {
  year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  hour12: false, timeZone: 'UTC',
});

export function formatRunTime(timestamp) {
  return typeof timestamp === 'string' && Number.isFinite(Date.parse(timestamp))
    ? `${runTimeFormatter.format(new Date(timestamp))} UTC` : '—';
}

export function runSelectionLabel(run) {
  return `${shortSha(run)} · Run ${formatRunTime(run.timestamp)}`;
}
