export const isJsonObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);

export function isJsonValue(value) {
  return value === null || typeof value === 'string' || typeof value === 'boolean'
    || typeof value === 'number' && Number.isFinite(value)
    || Array.isArray(value) && value.every(isJsonValue)
    || isJsonObject(value) && Object.entries(value).every(([key, item]) => Boolean(key.trim()) && isJsonValue(item));
}

export function typedJsonIdentity(value) {
  if (Array.isArray(value)) return `[${value.map(typedJsonIdentity).join(',')}]`;
  if (isJsonObject(value)) {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${typedJsonIdentity(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}
