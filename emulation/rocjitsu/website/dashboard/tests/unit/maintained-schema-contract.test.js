import { readFileSync } from 'node:fs';
import { expect, test } from 'vitest';

const document = readFileSync(new URL('../../docs/schema-1.md', import.meta.url), 'utf8');
const section = (heading) => document.split(`## ${heading}\n`)[1]?.split('\n## ')[0] ?? '';

test('maintained contract records implemented rejection and unresolved numeric acceptance', () => {
  const status = section('Implementation status');
  expect(status).toContain('shared browser/CLI validation path');
  expect(status).toContain('Historical schemas are rejected');
  expect(status).toContain('Numeric precision remains an unresolved publication gate');
  expect(status).toContain('No compatibility migration is promised');

  const policy = section('Rejection and export boundary');
  expect(policy).toContain('reject unversioned legacy input');
  expect(policy).toContain('old-shape');
  expect(policy).toContain('plugin/comparison identity');
  expect(policy).toContain('schema 2');
  expect(policy).toContain('Do not skip an');
  expect(policy).toContain('invalid historical record as if it were a valid maintained publication');
});

test('maintained export policy preserves published data without promising runner diagnostics', () => {
  const policy = section('Rejection and export boundary');
  expect(policy).toContain('parsed published `{index, catalogs, runs}`');
  expect(policy).toContain('through `sourceData`');
  expect(policy).toContain('regardless of filters');
  expect(policy).toContain('not byte-identical input JSON');
  expect(policy).toContain('Runner `exit_code`, stdout/stderr');
  expect(policy).toContain('not promised published export fields');
});

test('maintained examples use literal policies and matching catalog membership', () => {
  const examples = [...document.matchAll(/```json\n([\s\S]*?)\n```/g)]
    .map(([, json]) => JSON.parse(json));
  expect(examples).toHaveLength(4);
  const [metadata, index, catalog, run] = examples;
  expect(metadata.schemaVersion).toBe(1);
  expect(run.schemaVersion).toBe(1);
  expect(index.runFiles).toEqual([`runs/default-branch/${run.id}.json`]);
  expect(run.testCatalog).toBe(`test-catalogs/${catalog.id}.json`);
  expect(run.configurations.map(({ target, thread_policy }) => `${target}/${thread_policy}`).sort())
    .toEqual(Object.keys(catalog.configurations).sort());

  for (const group of run.configurations) {
    expect(['single', 'default']).toContain(group.thread_policy);
    expect(group.results.map(({ testId }) => testId).sort())
      .toEqual([...catalog.configurations[`${group.target}/${group.thread_policy}`]].sort());
    for (const result of group.results) {
      expect(result.thread_policy).toBe(group.thread_policy);
      if (result.status === 'completed') {
        const samples = [...result.timing_results_s].sort((left, right) => left - right);
        const middle = Math.floor(samples.length / 2);
        const median = samples.length % 2 ? samples[middle] : (samples[middle - 1] + samples[middle]) / 2;
        expect(result.durationSeconds).toBe(median);
        expect(result.error).toBeNull();
      } else {
        expect(['failed', 'timeout']).toContain(result.status);
        expect(result.durationSeconds).toBeNull();
      }
    }
  }

  expect(catalog.tests[0].problem.shape).toEqual([16, 16, 16]);
  expect(catalog.tests[0].problem.options).toEqual({ transpose: false });
  expect(catalog.tests[0].problem.note).toBeNull();
});
