# Website, data, and publication

## Source map

Paths below are relative to `emulation/rocjitsu/website/dashboard/`.

```text
src/main.jsx → src/App.jsx             # start React; coordinate loading and pages
src/components/                       # pages, charts, tables, pickers
src/hooks/useDashboardState.js         # filters, selections, URL/history state
src/data/dashboardData.js             # fetch publication JSON
src/data/dashboardValidation.js       # validate and normalize it
src/data/runSchema.js                 # maintained version and configuration identity
src/data/selectors.js                  # derive chart/comparison data
src/config/metadata.json              # bundled settings and target run schema
scripts/dashboard-data/                # prepare and stage benchmark publications
vite.config.js                        # build assets and select the data source
```

This is a static React website. The browser fetches JSON and computes the displayed comparisons; there is no dashboard application server in production.

## Website deployment versus data publication

These are separate workflows and Git branches:

| What | Repository-root workflow | Destination |
| --- | --- | --- |
| Website HTML/JS/CSS | `.github/workflows/rocjitsu-publish-website.yml` | `gh-pages:rocjitsu-dashboard/` |
| Benchmark JSON | `.github/workflows/rocjitsu-benchmarks.yml` | `gh-pages-rocjitsu:rocjitsu-dashboard/data/` |

Website publication checks current `develop` against the last published source revision, verifies/builds changed sites, then publishes dashboard `dist/`. Manual publication also requires `develop`. Production assets do not contain benchmark fixtures or measurements. Keep fixture JSON out of both publication destinations. Updating bundled settings requires a website rebuild; publishing new measurements does not.

```text
Website URL:
https://rocm.github.io/rocm-systems/rocjitsu-dashboard/

Production JSON base URL:
https://raw.githubusercontent.com/ROCm/rocm-systems/refs/heads/gh-pages-rocjitsu/rocjitsu-dashboard/data/
```

The base URL comes from `scripts/dashboard-data-source.mjs`; `src/data/publishedDataUrls.js` constructs the index URL. Fixture/local-data modes use `./data/`: fixtures come from `tests/fixtures/data/`, or `DASHBOARD_DATA_DIR` supplies a local directory.

## What each JSON file contains

| File | Information |
| --- | --- |
| `src/config/metadata.json` | Target run `schemaVersion`, repository URL, Beta flag, canonical branch. Bundled, never fetched from the data branch. |
| `data/index.json` | Publication time and the complete list of visible run-file paths. |
| `data/test-catalogs/<id>.json` | Workload definitions and target/policy membership. No measured timings. |
| `data/runs/default-branch/<id>.json` | A develop attempt: schema version, source commit, execution/machine/environment, configurations, timings, statuses, diagnostics. |
| `data/runs/side-branches/<id>.json` | The same run format for any other branch. Flat directory, not one directory per branch. |

```text
index.runFiles[] → run file
run.testCatalog → catalog file
run result.testId → catalog.tests[].id
```

## Browser loading

```text
Fetch index.json
  → fetch every listed run
  → fetch the distinct catalogs needed by included runs
  → strict JSON text parsing and maintained version/shape validation
  → validate and normalize
  → selectors → UI
```

Unindexed files are not scanned. The [maintained schema contract](schema-1.md) specifies legacy rejection and parsed-published export preservation; its implementation-status section distinguishes local compatibility from unresolved numeric acceptance and rollout. The mutable index bypasses cache; immutable runs/catalogs can use cache. “Reload all data” cache-busts requests.

## Preparing and publishing measurements

The benchmark workflow runs on relevant develop pushes or manual dispatch, not a scheduled trigger. It invokes the corpus `performance-v1.toml` manifest once with both target configs and no target, case, or thread-policy selector, using the manifest's sampling defaults. The paired temporary corpus pin `6186d5c8bcd5e9bc93f7406e7cb50ed2a7698621` selects all TOML-supported policies when the selector is omitted. The original temporary-pin TODO remains an uncommitted local reminder, outside this implementation commit, until the corpus merge and final-pin verification gates are satisfied; this pairing does not establish native or hosted execution acceptance. The runner selects supported combinations and checkpoints one consolidated `run.json`, alongside per-target/policy diagnostics. Before a side-branch benchmark starts, a lightweight job snapshots `develop` and records the dispatched commit's merge-base with that immutable revision. The optional `pull_request_number` input also records an open same-repository PR when its head branch and SHA match the selected workflow branch; without that input, the run keeps its base but has no PR metadata. Develop runs reject the PR input and omit both fields.

```text
Run supported target/policy combinations in one corpus invocation
  → upload raw result directories as a GitHub Actions artifact
  → publish job downloads that artifact
  → checkout gh-pages-rocjitsu, the source dashboard scripts and pinned corpus manifest
  → prepare-dashboard-data.py (once)
  → copy the run and catalog without overwriting existing files
  → update-dashboard-index.py
  → validate-dashboard-data.mjs
  → Git commit + push
```

- **Prepare:** pass the consolidated artifact's `run.json` once via `--raw-run`; validate per-result policy, identity, operation, samples and provenance; lowercase commit SHAs; calculate median completed timings; and generate one maintained schema-1 run plus its suite-named catalog in an isolated build directory. Trusted `--corpus-dir`, repository-relative `--manifest` and `--expected-corpus-sha` inputs select committed TOML, not raw-artifact declarations. Each supplied raw input must independently match the full declared tuple set and typed workload definitions; diagnostic subsets reject even on first publication. Full finalized failures remain publishable. Preserve accepted sample order and corpus IDs. Failed/timeout rows retain partial samples but have null duration. Policies remain literal `single`/`default`, in groups and results, with catalog keys `target/policy`. Problem values retain JSON types recursively; environment facts remain scalar. See [implementation status](schema-1.md#implementation-status) for unresolved numeric precision acceptance before publication. Shared environment protocol facts are `execution.warmups`, `execution.samples`, `execution.timeout_seconds`, and `execution.benchmark_suite`, without policy prefixes or target config hashes.
- **Copy:** place the run and catalog at their fixed publication paths without overwriting them. An identical existing file is an idempotent retry; different content at the same path is an error.
- **Index:** append the run path when absent. An already indexed run preserves `index.json` bytes and `generatedAt` exactly.
- **Publish:** validate the complete dataset and stage only the index, run and catalog. Preserve the existing maximum of three normal push attempts: retry only confirmed non-fast-forward conflicts after reloading the branch, reapplying unchanged immutable inputs and validating the full index. Identical retries are idempotent; immutable conflicts, validation and other push errors fail immediately. No force-push or benchmark rerun.

The Actions artifact only transfers raw results between jobs. The Git push makes dashboard JSON available.

## Immutable means “do not change an existing resource”

```text
Run/catalog: same path + same JSON content → reuse; no rewrite
Run/catalog: same path + different content → error
Changed catalog content                  → new manifest name/catalog file
New benchmark attempt                    → new run ID/file
index.json                               → mutable; updated to reference runs
```

Timing, status, error and sampling changes do not change the catalog. The catalog ID
is exactly `execution_summary.benchmark_suite`, equal to the pinned manifest name.
The publisher checks out that manifest at the same immutable corpus pin as the
runner, without persisted credentials. Changed membership/definitions require a
new manifest name; incompatible workload definitions also require new workload IDs.
Keep old run/catalog files for cached indexes. Catalog menu/table dates describe
the latest published develop commit using each catalog (UTC), not catalog creation
or execution time. Unknown URL identities remain unavailable until the user
chooses an available catalog or Shared benchmarks; export remains unfiltered.

Contract and examples: [maintained schema 1](schema-1.md). Commands: [build and test](build-and-test.md).
