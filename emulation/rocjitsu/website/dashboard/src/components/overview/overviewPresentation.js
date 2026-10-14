// Pure presentation navigation; gaps are not eligible inspection points.
export function trendKeyIndex(indexes, current, key) {
  if (key === 'Escape' || !indexes.length) return null;
  if (key === 'Home') return indexes[0];
  if (key === 'End') return indexes.at(-1);
  const position = indexes.indexOf(current);
  if (key === 'ArrowRight') return indexes[Math.min(indexes.length - 1, position + 1)];
  if (key === 'ArrowLeft') return indexes[Math.max(0, position < 0 ? indexes.length - 1 : position - 1)];
  return current;
}

export function nearestTrendIndex(history, x) {
  if (!Number.isFinite(x)) return null;
  const nearest = history.slots.reduce((nearest, slot, index) => {
    return nearest == null || Math.abs(slot.x - x) < Math.abs(history.slots[nearest].x - x) ? index : nearest;
  }, null);
  return nearest != null && history.slots[nearest].run && history.rows.some((row) => Number.isFinite(row.points[nearest]?.speedup)) ? nearest : null;
}

export function recentRunsPage(rowCount, requestedPage) {
  const page = Math.max(0, Math.min(requestedPage, Math.ceil(rowCount / 20) - 1));
  const start = page * 20;
  return { page, start, end: Math.min(rowCount, start + 20) };
}
