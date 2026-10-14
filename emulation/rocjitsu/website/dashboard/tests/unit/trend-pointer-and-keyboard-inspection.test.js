import { expect, test } from 'vitest';
import { nearestTrendIndex, trendKeyIndex } from '../../src/components/overview/overviewPresentation.js';

test('magnetic column resolution considers the nearest slot before measurement eligibility', () => {
  const projection = { slots: [{ x: 0, run: {} }, { x: 1, run: {} }, { x: 2, run: {} }],
    rows: [{ points: [{ speedup: 1 }, { speedup: null }, { speedup: 1.2 }] },
      { points: [{ speedup: null }, { speedup: null }, { speedup: 0.9 }] }] };
  expect(nearestTrendIndex(projection, 1)).toBeNull();
  expect(nearestTrendIndex(projection, 2)).toBe(2);
  expect(nearestTrendIndex(projection, NaN)).toBeNull();
});
test('keyboard navigation skips gaps and supports first/last/clear', () => {
  expect(trendKeyIndex([0, 2, 5], null, 'ArrowRight')).toBe(0);
  expect(trendKeyIndex([0, 2, 5], 0, 'ArrowRight')).toBe(2);
  expect(trendKeyIndex([0, 2, 5], 2, 'ArrowLeft')).toBe(0);
  expect(trendKeyIndex([0, 2, 5], null, 'End')).toBe(5);
  expect(trendKeyIndex([0, 2, 5], 5, 'Home')).toBe(0);
  expect(trendKeyIndex([0, 2, 5], 2, 'Escape')).toBeNull();
});
