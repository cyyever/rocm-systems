import { isJsonValue, isSupportedNumber, isTimingNumber, typedJsonIdentity } from './jsonValues.js';
import { CURRENT_RUN_SCHEMA_VERSION, THREAD_POLICIES, CONFIGURATION_PATTERN, configurationKey, publishedRunPath, runSchemaVersion } from './runSchema.js';
import { DASHBOARD_SITE_CONFIG } from '../config/siteConfig.js';
import { backfillRunIds, compareRunExecution, sortRunsByCommit } from './runOrdering.js';

export const CURRENT_SCHEMA_VERSION = CURRENT_RUN_SCHEMA_VERSION;
export const RUN_FILE_PATTERN = /^runs\/(?:default-branch|side-branches)\/[A-Za-z0-9._-]+\.json$/;
export const CATALOG_FILE_PATTERN = /^test-catalogs\/[A-Za-z0-9._-]+\.json$/;
const SHA = /^[0-9a-f]{40}$/;
const TOKEN = /^[A-Za-z0-9._-]+$/;
const CONFIGURATION = CONFIGURATION_PATTERN;
const ISO = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|([+-])(\d{2}):(\d{2}))$/;
const hasText = (value) => typeof value === 'string' && Boolean(value.trim());
const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const scalar = (value) => typeof value === 'string' || typeof value === 'boolean' || isSupportedNumber(value);
const sameSet = (left, right) => {
  if (left.length !== right.length) return false;
  const sortedLeft = [...left].sort();
  const sortedRight = [...right].sort();
  return sortedLeft.every((value, index) => value === sortedRight[index]);
};
const identity = (value) => JSON.stringify(value);
const environmentIdentity = (environment) => identity(environment.map(({ key, value }) => [key, value]).sort(([a], [b]) => a.localeCompare(b)));
const definitionIdentity = (test) => typedJsonIdentity([test.suite, test.name, test.operation, test.problem]);

function isIsoTimestamp(value) {
  if (typeof value !== 'string') return false;
  const match = ISO.exec(value);
  if (!match || !Number.isFinite(Date.parse(value))) return false;
  const [, y, m, d, h, min, s, , oh = '0', om = '0'] = match;
  const date = new Date(`${y}-${m}-${d}T00:00:00.000Z`);
  return date.getUTCFullYear() === Number(y) && date.getUTCMonth() + 1 === Number(m)
    && date.getUTCDate() === Number(d) && Number(h) <= 23 && Number(min) <= 59
    && Number(s) <= 59 && Number(oh) <= 23 && Number(om) <= 59;
}

function safeUrl(value, github = false) {
  if (!hasText(value)) return false;
  try {
    const url = new URL(value);
    return !url.username && !url.password && ['http:', 'https:'].includes(url.protocol)
      && (!github || url.protocol === 'https:' && url.hostname === 'github.com' && !url.search && !url.hash);
  } catch { return false; }
}

export function validatePublishedManifest(index) {
  if (!isIsoTimestamp(index?.generatedAt) || !Array.isArray(index?.runFiles)) throw new Error('Expected index generatedAt strict ISO timestamp and runFiles array');
  for (const name of index.runFiles) {
    if (typeof name !== 'string' || !RUN_FILE_PATTERN.test(name)) throw new Error(`Invalid run filename: ${String(name)}`);
  }
  if (new Set(index.runFiles).size !== index.runFiles.length) throw new Error('Duplicate run filename');
}

export function validateDashboardSiteConfig(siteConfig) {
  if (!safeUrl(siteConfig?.repository)) throw new Error('Expected dashboard site configuration to contain a safe HTTP repository URL');
  if (typeof siteConfig.isBeta !== 'boolean' || siteConfig.canonicalBranch !== 'develop') throw new Error('Expected site configuration isBeta boolean and canonicalBranch develop');
}

function envelope(value, fields, label) {
  if (!object(value) || Object.keys(value).some((key) => !fields.includes(key))) throw new Error(`${label} contains unsupported fields or old-shaped schema-1 input`);
}

function validateCatalog(catalog, file) {
  envelope(catalog, ['benchmark_suite', 'benchmark_definitions', 'membership'], `Test catalog ${file}`);
  const id = catalog.benchmark_suite;
  if (!CATALOG_FILE_PATTERN.test(file) || typeof id !== 'string' || !TOKEN.test(id) || ['.', '..'].includes(id) || id !== file.slice(14, -5)
    || !object(catalog.benchmark_definitions) || !Object.keys(catalog.benchmark_definitions).length || !object(catalog.membership) || !Object.keys(catalog.membership).length) {
    throw new Error(`Test catalog ${file} does not match the maintained schema-1 catalog contract`);
  }
  const tests = Object.entries(catalog.benchmark_definitions).map(([testId, definition]) => {
    envelope(definition, ['suite', 'name', 'operation', 'problem'], `Test definition ${testId}`);
    if (!hasText(testId) || !hasText(definition.suite) || !hasText(definition.name) || !hasText(definition.operation)
      || !object(definition.problem) || Object.entries(definition.problem).some(([key, value]) => !hasText(key) || !isJsonValue(value))) throw new Error(`Test catalog ${file} contains an invalid or duplicate test definition`);
    return { id: testId, ...definition };
  });
  const configurations = {};
  for (const [target, policies] of Object.entries(catalog.membership)) {
    if (!TOKEN.test(target) || !object(policies) || !Object.keys(policies).length) throw new Error(`Test catalog ${file} contains an invalid configuration`);
    for (const [policy, members] of Object.entries(policies)) {
      const key = configurationKey(target, policy);
      if (!CONFIGURATION.test(key) || !Array.isArray(members) || !members.length || new Set(members).size !== members.length
        || members.some((member) => typeof member !== 'string' || !Object.hasOwn(catalog.benchmark_definitions, member))) throw new Error(`Test catalog ${file} contains an invalid configuration ${key}`);
      Object.defineProperty(configurations, key, { value: members, enumerable: true });
    }
  }
  return { id, tests, configurations };
}

export function validatePublishedResult(result) {
  envelope(result, ['id', 'status', 'timing_results_s', 'error'], 'Result');
  if (!hasText(result.id)) throw new Error('Result must contain an id');
  if (!['completed', 'failed', 'timeout'].includes(result.status)) throw new Error(`Result ${result.id} has invalid status`);
  if (!Object.hasOwn(result, 'error') || result.error !== null && !hasText(result.error)) throw new Error(`Result ${result.id} error must be a non-empty string or null`);
  if (result.status === 'completed' && result.error !== null) throw new Error(`Completed result ${result.id} cannot contain an error`);
  const samples = result.timing_results_s;
  if (!Array.isArray(samples) || samples.some((sample) => !isTimingNumber(sample)) || result.status === 'completed' && !samples.length) throw new Error(`Result ${result.id} timing_results_s must contain positive finite samples within supported numeric timing ceiling, nonempty when completed`);
  return result;
}

function durationFor(result) {
  if (result.status !== 'completed') return null;
  const samples = [...result.timing_results_s].sort((a, b) => a - b);
  const middle = Math.floor(samples.length / 2);
  return samples.length % 2 ? samples[middle] : (samples[middle - 1] + samples[middle]) / 2;
}

function normalizedEnvironment(provenance, summary) {
  const details = new Map();
  for (const [section, values] of Object.entries(provenance)) for (const [key, value] of Object.entries(values)) {
    if (section === 'rocjitsu' && ['rocjitsu_commit_sha', 'rocjitsu_commit_timestamp', 'target_config_sha256', 'workflow_commit_sha'].includes(key)
      || section === 'auxiliary' && key === 'tensile_commit_sha') continue;
    const name = `${section}.${key}`;
    details.set(name, { key: name, label: name, value: scalar(value) ? value : typedJsonIdentity(value) });
  }
  // Match the producer's existing scalar projection: protocol overrides open facts.
  for (const key of ['warmups', 'samples', 'timeout_seconds', 'benchmark_suite']) {
    const name = `execution.${key}`;
    details.set(name, { key: name, label: name, value: summary[key] });
  }
  return [...details.values()].sort((a, b) => a.key.localeCompare(b.key));
}

function normalizeRun(run, catalog, generatedAt) {
  envelope(run, ['schemaVersion', 'id', 'benchmark_catalog', 'source', 'execution', 'execution_summary', 'provenance', 'configurations'], 'Run');
  const { source, execution, execution_summary: summary, provenance } = run;
  envelope(source, ['branch', 'message', 'base', 'pullRequest'], `Run ${run.id} source`);
  envelope(execution, ['trigger', 'machine_label'], `Run ${run.id} execution`);
  envelope(summary, ['benchmark_suite', 'timestamp', 'finished_at', 'wall_time_s', 'warmups', 'samples', 'timeout_seconds'], `Run ${run.id} execution_summary`);
  if (!hasText(source.branch) || Object.hasOwn(source, 'message') && !hasText(source.message) || !['auto', 'manual'].includes(execution.trigger) || !hasText(execution.machine_label)
    || !object(provenance) || ['auxiliary', 'corpus', 'machine', 'rocjitsu'].some((key) => !object(provenance[key]))
    || Object.values(provenance).some((values) => !object(values) || Object.entries(values).some(([key, value]) => !hasText(key) || !isJsonValue(value)))
    || !Array.isArray(run.configurations) || !run.configurations.length) throw new Error(`Run ${run.id} does not match the maintained schema-1 run contract`);
  const native = provenance.rocjitsu; const corpus = provenance.corpus;
  if (![native.rocjitsu_commit_sha, native.workflow_commit_sha, corpus.corpus_commit_sha, provenance.auxiliary.tensile_commit_sha].every((sha) => typeof sha === 'string' && SHA.test(sha))
    || !Object.hasOwn(native, 'rocm_sdk_version') || native.rocm_sdk_version !== null && !hasText(native.rocm_sdk_version)
    || ['hostname', 'platform', 'kernel', 'cpu'].some((key) => !hasText(provenance.machine[key]))) throw new Error(`Run ${run.id} has invalid provenance commit or machine facts`);
  if (![native.rocjitsu_commit_timestamp, corpus.corpus_commit_timestamp, summary.timestamp, summary.finished_at].every(isIsoTimestamp)
    || !Number.isInteger(summary.warmups) || !isSupportedNumber(summary.warmups) || summary.warmups < 0
    || !Number.isInteger(summary.samples) || !isSupportedNumber(summary.samples) || summary.samples < 1
    || !isSupportedNumber(summary.timeout_seconds) || summary.timeout_seconds <= 0 || !isSupportedNumber(summary.wall_time_s) || summary.wall_time_s < 0) throw new Error(`Run ${run.id} has invalid execution summary`);
  if (Date.parse(native.rocjitsu_commit_timestamp) > Date.parse(summary.timestamp) || Date.parse(corpus.corpus_commit_timestamp) > Date.parse(summary.timestamp)
    || Date.parse(summary.timestamp) > Date.parse(summary.finished_at) || Date.parse(summary.finished_at) > Date.parse(generatedAt)) throw new Error(`Run ${run.id} must be committed before execution start, completed after start and completed by publication`);
  if (summary.benchmark_suite !== catalog.id) throw new Error(`Run ${run.id} execution_summary.benchmark_suite must equal catalog ID ${catalog.id}`);
  if (Object.hasOwn(source, 'base')) {
    envelope(source.base, ['branch', 'commit'], 'Source base');
    if (!hasText(source.base.branch) || source.base.branch === source.branch || typeof source.base.commit !== 'string' || !SHA.test(source.base.commit)) throw new Error(`Run ${run.id} has an invalid source base`);
  }
  if (Object.hasOwn(source, 'pullRequest')) {
    envelope(source.pullRequest, ['number', 'url'], 'Pull request');
    if (!source.base || !Number.isSafeInteger(source.pullRequest.number) || source.pullRequest.number <= 0
      || Object.hasOwn(source.pullRequest, 'url') && (!safeUrl(source.pullRequest.url, true) || !new URL(source.pullRequest.url).pathname.endsWith(`/pull/${source.pullRequest.number}`))) throw new Error(`Run ${run.id} has an invalid pullRequest`);
  }
  const definitions = new Map(catalog.tests.map((test) => [test.id, test]));
  const seen = new Set();
  const tests = run.configurations.flatMap((configuration) => {
    envelope(configuration, ['target', 'thread_policy', 'benchmark_results'], 'Configuration');
    const { target, thread_policy, benchmark_results: results } = configuration;
    const key = configurationKey(target, thread_policy);
    if (!THREAD_POLICIES.includes(thread_policy) || !hasText(target) || !CONFIGURATION.test(key) || !Object.hasOwn(catalog.configurations, key) || seen.has(key) || !Array.isArray(results)) throw new Error(`Run ${run.id} has an invalid or duplicate configuration ${key}`);
    seen.add(key);
    results.forEach(validatePublishedResult);
    const ids = results.map(({ id }) => id);
    if (new Set(ids).size !== ids.length || !sameSet(ids, catalog.configurations[key])) throw new Error(`Run ${run.id} must contain exactly one result per ${key} catalog workload`);
    return results.map((result) => ({ ...definitions.get(result.id), status: result.status, durationSeconds: durationFor(result), error: result.error, timing_results_s: [...result.timing_results_s], testId: `${key}:${result.id}`, logicalTestId: result.id, target, thread_policy, mode: thread_policy }));
  });
  if (!sameSet([...seen], Object.keys(catalog.configurations))) throw new Error(`Run ${run.id} must contain exactly the catalog configuration keys`);
  const environment = normalizedEnvironment(provenance, summary);
  const sourceDetails = [
    { key: 'rocjitsu.workflow_commit_sha', label: 'Workflow commit', value: native.workflow_commit_sha },
    { key: 'auxiliary.tensile_commit_sha', label: 'Tensile commit', value: provenance.auxiliary.tensile_commit_sha },
  ];
  return {
    runId: run.id, testCatalog: run.benchmark_catalog, catalogId: catalog.id,
    timestamp: summary.finished_at, commitTimestamp: native.rocjitsu_commit_timestamp, trigger: execution.trigger, machineId: execution.machine_label,
    targets: [...new Set(run.configurations.map(({ target }) => target))], modes: THREAD_POLICIES.filter((mode) => run.configurations.some((c) => c.thread_policy === mode)),
    branch: source.branch, ...(source.base ? { sourceBase: { ...source.base } } : {}), ...(source.pullRequest ? { pullRequest: { ...source.pullRequest } } : {}),
    environmentId: environmentIdentity(environment),
    provenance: { rocjitsuCommitSha: native.rocjitsu_commit_sha, ...(source.message ? { commitMessage: source.message } : {}), details: [...environment, ...sourceDetails] },
    configurations: run.configurations.map(({ target, thread_policy }) => ({ target, thread_policy })), tests,
  };
}

function buildDashboardData(raw) {
  const sourceRuns = raw?.allRuns ?? raw?.runs;
  if (raw?.schemaVersion !== 1 || !Array.isArray(sourceRuns) || !Array.isArray(raw.testCatalog)) throw new Error('Expected maintained schema-1 normalized data with runs and testCatalog');
  for (const run of sourceRuns) {
    if (!hasText(run?.runId) || !Array.isArray(run.tests) || !Array.isArray(run.configurations) || !isIsoTimestamp(run.timestamp)
      || !isIsoTimestamp(run.commitTimestamp) || !hasText(run.branch)) throw new Error('Invalid normalized dashboard run');
  }
  const allRuns = [...sourceRuns].sort(compareRunExecution);
  const runs = allRuns.filter(({ branch }) => branch === (raw.canonicalBranch ?? 'develop'));
  return { ...raw, canonicalBranch: raw.canonicalBranch ?? 'develop', allRuns, runs,
    targets: [...new Set(allRuns.flatMap(({ targets }) => targets))].sort(), suites: [...new Set(raw.testCatalog.map(({ suite }) => suite))].sort(), modes: [...THREAD_POLICIES],
    latestRun: runs.at(-1) ?? null, latestCommitRun: sortRunsByCommit(runs).at(-1) ?? null, backfillRunIds: backfillRunIds(runs) };
}

export function validatePublishedDashboardData({ index, runs, runErrors = [], catalogs = {}, catalogErrors = {}, siteConfig = DASHBOARD_SITE_CONFIG }) {
  validatePublishedManifest(index);
  validateDashboardSiteConfig(siteConfig);
  if (!Array.isArray(runs) || runs.length !== index.runFiles.length) throw new Error('Loaded runs must match index runFiles');
  const normalizedCatalogs = new Map(); const sourceCatalogs = new Map();
  const normalizedRuns = []; const failures = []; const sourceIds = new Set();
  index.runFiles.forEach((file, indexPosition) => {
    try {
      if (runErrors[indexPosition]) throw runErrors[indexPosition];
      const sourceRun = runs[indexPosition];
      if (typeof sourceRun?.id !== 'string' || !TOKEN.test(sourceRun.id) || ['.', '..'].includes(sourceRun.id)) throw new Error('Run does not match the maintained schema-1 run contract: invalid ID');
      if (sourceIds.has(sourceRun.id)) throw new Error(`Duplicate run ID ${sourceRun.id}`);
      sourceIds.add(sourceRun.id);
      if (file.split('/').at(-1) !== `${sourceRun.id}.json`) throw new Error(`Run ${sourceRun.id} filename must match its ID`);
      const catalogFile = sourceRun.benchmark_catalog;
      if (typeof catalogFile === 'string' && CATALOG_FILE_PATTERN.test(catalogFile) && Object.hasOwn(catalogs, catalogFile)) {
        sourceCatalogs.set(catalogFile, catalogs[catalogFile]);
      }
      runSchemaVersion(sourceRun);
      if (file !== publishedRunPath(sourceRun, siteConfig.canonicalBranch)) {
        throw new Error(`Run ${sourceRun.id} filename must match its ID and branch directory`);
      }
      if (typeof catalogFile !== 'string' || !CATALOG_FILE_PATTERN.test(catalogFile)) throw new Error(`Run ${sourceRun.id} references an invalid test catalog`);
      if (catalogErrors[catalogFile]) throw catalogErrors[catalogFile];
      const catalog = validateCatalog(catalogs[catalogFile], catalogFile);
      normalizedCatalogs.set(catalogFile, catalog);
      normalizedRuns.push(normalizeRun(sourceRun, catalog, index.generatedAt));
    } catch (error) { failures.push(`- ${file}: ${error.message}`); }
  });
  if (failures.length) throw new Error(`Dashboard data failed validation:\n${failures.join('\n')}`);
  const commits = new Map(); const definitions = new Map();
  for (const run of normalizedRuns) {
    const sha = run.provenance.rocjitsuCommitSha; const timestamp = Date.parse(run.commitTimestamp);
    if (commits.has(sha) && commits.get(sha) !== timestamp) throw new Error(`Commit ${sha} has conflicting committedAt values`);
    commits.set(sha, timestamp);
  }
  for (const [file, catalog] of normalizedCatalogs) for (const definition of catalog.tests) {
    const previous = definitions.get(definition.id);
    if (previous && (definitionIdentity(previous) !== definitionIdentity(definition)
     )) throw new Error(`Test ${definition.id} is defined differently in ${file}; publish a new test ID`);
    definitions.set(definition.id, definition);
  }
  const sourceData = { index, catalogs: Object.fromEntries(sourceCatalogs), runs };
  const data = buildDashboardData({ repository: siteConfig.repository, isBeta: siteConfig.isBeta, canonicalBranch: siteConfig.canonicalBranch, schemaVersion: CURRENT_SCHEMA_VERSION, generatedAt: index.generatedAt, testCatalog: [...definitions.values()], catalogs: Object.fromEntries(normalizedCatalogs), runs: normalizedRuns });
  return { data, sourceData };
}
