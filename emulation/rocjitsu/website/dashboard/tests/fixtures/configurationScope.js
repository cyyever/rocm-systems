// Test-only publication editing. A sparse run requires its own equally sparse
// catalog; never infer production membership or repair malformed input this way.
export function setFixtureConfigurations(publication, run, configurations) {
  const original = publication.catalogs[run.testCatalog];
  const catalog = structuredClone(original);
  catalog.id = `${original.id}-${run.id}-scope`;
  catalog.configurations = Object.fromEntries(configurations.map(({ target, thread_policy, results }) => [
    `${target}/${thread_policy}`, results.map(({ testId }) => testId),
  ]));
  run.configurations = configurations;
  run.testCatalog = `test-catalogs/${catalog.id}.json`;
  publication.catalogs[run.testCatalog] = catalog;
  run.environment.find(({ key }) => key === 'execution.benchmark_suite').value = catalog.id;
}
