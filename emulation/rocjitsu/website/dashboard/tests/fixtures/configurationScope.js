// Test-only publication editing. Never repair malformed production membership.
export function setFixtureConfigurations(publication, run, configurations) {
  const catalog = structuredClone(publication.catalogs[run.benchmark_catalog]);
  catalog.benchmark_suite = `${catalog.benchmark_suite}-${run.id}-scope`;
  catalog.membership = {};
  for (const { target, thread_policy, benchmark_results } of configurations) {
    catalog.membership[target] ??= {};
    catalog.membership[target][thread_policy] = benchmark_results.map(({ id }) => id);
  }
  run.configurations = configurations;
  run.benchmark_catalog = `test-catalogs/${catalog.benchmark_suite}.json`;
  publication.catalogs[run.benchmark_catalog] = catalog;
  run.execution_summary.benchmark_suite = catalog.benchmark_suite;
}
