const TARGET_COLORS = {
  gfx1250: '#2166C1',
  gfx950: '#C25430',
  gfx1201: '#7450B8',
};

const targetFallbackColors = ['#2166C1', '#C25430', '#7450B8', '#14826F', '#B7791F'];

export function targetColor(target, index = 0) {
  return Object.hasOwn(TARGET_COLORS, target) ? TARGET_COLORS[target] : targetFallbackColors[index % targetFallbackColors.length];
}

// Shared by Overview metric values and the corresponding trend lines.
export function configurationColor(row, index = 0) {
  return row.mode === 'default'
    ? ({ gfx1250: '#14826F', gfx950: '#7450B8' }[row.target] ?? targetColor(row.target, index + 2))
    : targetColor(row.target, index);
}
