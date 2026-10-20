import metadata from '../config/metadata.json' with { type: 'json' };

export const CURRENT_RUN_SCHEMA_VERSION = metadata.schemaVersion;
export const THREAD_POLICIES = Object.freeze(['single', 'default']);
export const CONFIGURATION_PATTERN = /^([A-Za-z0-9._-]+)\/(single|default)$/;
export const configurationKey = (target, policy) => `${target}/${policy}`;
export const hasConfiguration = (run, target, policy) => (run?.configurations ?? [])
  .some((configuration) => configuration.target === target && configuration.thread_policy === policy);

export function publishedRunPath(run, canonicalBranch = 'develop') {
  const directory = run.source?.branch === canonicalBranch ? 'default-branch' : 'side-branches';
  return `runs/${directory}/${run.id}.json`;
}

export function runSchemaVersion(run) {
  if (run === null || typeof run !== 'object' || Array.isArray(run)) throw new Error('Run must be an object');
  if (run.schemaVersion !== 1) {
    throw new Error(`Run ${run.id ?? '(unknown)'} has unsupported schema version ${run.schemaVersion ?? '(missing)'}; expected maintained schema 1`);
  }
  if (['targets', 'plugin', 'comparisonId', 'testCatalog', 'environment'].some((key) => Object.hasOwn(run, key))) {
    throw new Error(`Run ${run.id ?? '(unknown)'} has legacy fields; expected maintained schema-1 run/catalog contract`);
  }
  return run.schemaVersion;
}
