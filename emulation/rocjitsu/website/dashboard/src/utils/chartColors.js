const TARGET_COLORS = {
  gfx1250: '#2166C1',
  gfx950: '#C25430',
  gfx1201: '#7450B8',
};

const targetFallbackColors = ['#2166C1', '#C25430', '#7450B8', '#14826F', '#B7791F'];

export function targetColor(target, index = 0) {
  return Object.hasOwn(TARGET_COLORS, target) ? TARGET_COLORS[target] : targetFallbackColors[index % targetFallbackColors.length];
}

// Same configuration identity in metric text, legends and trend lines. The dark
// variants retain each hue while meeting normal-text contrast on the card.
const darkConfigurationColors = {
  '#2166C1': '#78a9ff', '#C25430': '#ff832b', '#7450B8': '#be95ff',
  '#14826F': '#3ddbd9', '#B7791F': '#f1c21b',
};

const defaultConfigurationColors = { gfx1250: '#14826F', gfx950: '#7450B8' };

export function configurationColor(row, index = 0, themeMode = 'light') {
  const color = row.mode === 'default'
    ? (Object.hasOwn(defaultConfigurationColors, row.target) ? defaultConfigurationColors[row.target] : targetColor(row.target, index + 2))
    : targetColor(row.target, index);
  return themeMode === 'dark' ? darkConfigurationColors[color] : color === '#B7791F' ? '#8a3800' : color;
}
