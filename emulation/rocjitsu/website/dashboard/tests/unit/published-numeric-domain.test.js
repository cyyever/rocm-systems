import { describe, expect, it } from 'vitest';
import { parsePublishedJson } from '../../src/data/publishedJson.js';
import { isJsonValue } from '../../src/data/jsonValues.js';
import { validatePublishedResult } from '../../src/data/dashboardValidation.js';

const result = (samples, status = 'completed') => ({ testId: 'numeric', status, error: null,
  durationSeconds: status === 'completed' ? samples[0] : null, timing_results_s: samples });

describe('supported publication numeric domain', () => {
  it.each(['9007199254740993', '9007199254740992', '9007199254740993.0', '9.007199254740993e15', '1e308', '1e-400', '9007199254740991.1', '-9.007199254740993e15'])('rejects unsupported text token %s before export', (token) => {
    expect(() => parsePublishedJson(`{"problem":{"nested":[${token}]}}`)).toThrow(/numeric/i);
  });
  it.each(['9007199254740991.0', '9.007199254740991e15', '0e999999', '-0e-999999'])('accepts safe numeric spelling %s', (token) => {
    expect(parsePublishedJson(`[${token}]`)).toEqual(JSON.parse(`[${token}]`));
  });
  it('rejects unsafe already-parsed recursive values', () => {
    expect(isJsonValue({ nested: [9007199254740992] })).toBe(false);
  });
  it.each([0, -1, Infinity, NaN, true, 1e308])('rejects invalid timing sample %s', (sample) => {
    expect(() => validatePublishedResult(result([sample], 'failed'))).toThrow();
  });
  it('rejects oversized completed and partial samples', () => {
    expect(() => validatePublishedResult(result([4503599627370496]))).toThrow();
    expect(() => validatePublishedResult(result([4503599627370496], 'failed'))).toThrow();
  });
  it('preserves accepted numbers and other JSON types', () => {
    const text = '{"a":[9007199254740991,-9007199254740991,1.25,5e-324,0,null,true,"9007199254740993"]}';
    expect(parsePublishedJson(text)).toEqual(JSON.parse(text));
    expect(isJsonValue(JSON.parse(text))).toBe(true);
  });
  it('accepts timing ceiling and ordinary odd/even fractional medians', () => {
    for (const samples of [[4503599627370495], [4503599627370495, 4503599627370495], [1.25], [1, 1.5], [1, 1.25, 2]]) {
      const row = result(samples);
      row.durationSeconds = samples[0] === 4503599627370495 ? samples[0] : samples.length === 2 ? 1.25 : samples.length === 3 ? 1.25 : samples[0];
      expect(validatePublishedResult(row)).toBe(row);
    }
  });
});
