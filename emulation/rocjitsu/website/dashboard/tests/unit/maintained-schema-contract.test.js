import { readFileSync } from 'node:fs';
import { expect, test } from 'vitest';

const document = readFileSync(new URL('../../docs/schema-1.md', import.meta.url), 'utf8');
const section = (heading) => document.split(`## ${heading}\n`)[1]?.split('\n## ')[0] ?? '';

test('maintained contract records implemented schema and numeric rejection', () => {
  const status = section('Implementation status');
  expect(status).toContain('shared browser/CLI validation path');
  expect(status).toContain('Historical schemas are rejected');
  expect(status).toContain('Unsupported numeric values are rejected');
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
  expect(run.benchmark_catalog).toBe(`test-catalogs/${catalog.benchmark_suite}.json`);
  expect(run.configurations.map(({ target, thread_policy }) => `${target}/${thread_policy}`).sort())
    .toEqual(Object.entries(catalog.membership).flatMap(([target, policies]) => Object.keys(policies).map((policy) => `${target}/${policy}`)).sort());
  for (const group of run.configurations) {
    expect(['single', 'default']).toContain(group.thread_policy);
    expect(group.benchmark_results.map(({ id }) => id).sort()).toEqual([...catalog.membership[group.target][group.thread_policy]].sort());
    for (const result of group.benchmark_results) {
      expect(Object.keys(result).sort()).toEqual(['error', 'id', 'status', 'timing_results_s']);
      if (result.status === 'completed') expect(result.error).toBeNull();
      else expect(['failed', 'timeout']).toContain(result.status);
    }
  }
  expect(catalog.benchmark_definitions.gemm.problem.shape).toEqual([16, 16, 16]);
  expect(catalog.benchmark_definitions.gemm.problem.options).toEqual({ transpose: false });
  expect(catalog.benchmark_definitions.gemm.problem.note).toBeNull();
});
