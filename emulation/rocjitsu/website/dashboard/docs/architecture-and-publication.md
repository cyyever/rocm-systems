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
| `data/runs/default-branch/<id>.json` | A develop attempt: schema version, source commit, execution summary/structured provenance, configurations, timings, statuses, diagnostics. |
| `data/runs/side-branches/<id>.json` | The same run format for any other branch. Flat directory, not one directory per branch. |

```text
index.runFiles[] → run file
run.benchmark_catalog → catalog file
run result.id → catalog.benchmark_definitions[id]
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

The benchmark workflow runs on relevant develop pushes or manual dispatch, not a scheduled trigger. It invokes the corpus `performance-v1.toml` manifest once with both target configs and no target, case, or thread-policy selector, using the manifest's sampling defaults. The selected corpus revision is defined by `CORPUS_SHA` in the [benchmark workflow](../../../../../.github/workflows/rocjitsu-benchmarks.yml). This configuration does not establish native or hosted execution acceptance. The runner selects supported combinations and checkpoints one consolidated `run.json`, alongside per-target/policy diagnostics. Before a side-branch benchmark starts, a lightweight job snapshots `develop` and records the dispatched commit's merge-base with that immutable revision. The optional `pull_request_number` input also records an open same-repository PR when its head branch and SHA match the selected workflow branch; without that input, the run keeps its base but has no PR metadata. Develop runs reject the PR input and omit both fields.

### Isolated preparation before measurement

The workflow creates a fresh owned `${RUNNER_TEMP}/rocjitsu-benchmark-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}`. `emulation/rocjitsu/scripts/prepare-benchmarks.py` keeps its venv, builds, wheelhouse, generated artifacts, logs and caches there, outside the runner-owned results directory. It rejects reused attempts, mismatched ownership and symbolic directory paths; cleanup removes only the verified owned attempt. Source checkouts remain unchanged and are checked before and after preparation phases.

Preparation uses Python 3.12, the corpus's exact SDK/benchmark requirement pins, full rocm-libraries source `dd77374194a3ea1a7258cd54f87af6747b6362a5`, and separate native nanobind source `9b3afa9dbdc23641daf26fadef7743e7127ff92f`. Dependency resolution records indexes, reports and package inventories while constraining the benchmark pins. Before builds, preflight requires CMake ≥3.25.2, SDK HIP/LLVMObjectYAML/ROCmCMakeBuildTools, ZLIB and OpenMP. A noneditable rocisa wheel uses an external backend build directory and the discovered installed `nanobind_DIR`; only the exact built wheel is installed into the owned venv. Native adapter and host-test builds instead use the separately pinned disconnected nanobind source. Builds use four jobs.

The explicit `ROCISA_BACKEND=native` and four SDK loader directories (`lib`, `lib/rocm_sysdeps/lib`, `lib/llvm/lib`, `lib/host-math/lib`) are retained. Preparation commands use an owned **writable** controlled working directory, not a source checkout or a read-only empty directory: the native capability probe can emit implicit `a.out`. Only that regular assembler-output filename is permitted there; foreign loader files reject. No upstream/ELF/compiler patch or speculative `GPU_TARGETS` rewrite is made. Wheel import checks record exact extension/library hashes, installed-wheel origin and loader mappings; this does not establish portable relocatability of the upstream wheel.

The helper runs the pinned generator sequentially for the four manifest-selected variants, with the exact selected shapes/targets and generator `CpuThreads=4`. It strips inherited `HCC_AMDGPU_TARGET` and sets that variable only in each generator's copied child environment, using the validated target for that variant. This suppresses the installed HIPCC's demonstrated implicit enumeration path without hard-coding a global gfx950 or leaking a target to unrelated preparation commands or later workflow steps. Command receipts record the effective target, not the whole inherited environment. It validates artifact/configuration hashes and provenance before exporting `PYTHON`, SDK/source paths, `TENSILE_CANDIDATE_ARTIFACTS` and `TENSILE_CANDIDATE_RUNNER`. Failed preparation prevents the measured suite; cases are never dropped and stale artifacts are never reused. Generator threads do not set simulator runtime policy. Local intercepted tests verify orchestration and rejection predicates, **not actual dependency installation, native generation, kernel execution or hosted acceptance**.

The existing 210-minute job ceiling remains: aggregate setup/checkouts/Rocjitsu build 25 minutes, dependency resolution 20, wheel/native preparation 45, sequential generation 45, performance 60, diagnostics/upload/cleanup reserve 15. Step limits and helper phase/process watchdogs fail rather than silently increase these ceilings; they are not completion-time predictions. On timeout the owned process group gets TERM, a bounded grace period, then KILL independently of leader exit; absent groups are handled safely, and failure receipts record whether the leader was reaped. Preparation diagnostics exclude files with symbolic ancestors or resolved paths outside the owned attempt and exclusively create a fresh archive without following or truncating existing output links/files. Preparation diagnostics have a separate attempt-specific artifact, 14-day retention, and an explicit inventory describing truncation/omission (at most 128 files, final 256 KiB per file). Upload handling precedes owned cleanup. Hard cancellation or job termination can prevent both upload and cleanup. Manual `publish_results=false` still disables the entire publisher job, not diagnostic handling.

```text
Prepare pinned dependencies, wheel, native adapter and four generated variants
  → validate preparation provenance and artifacts
  → run supported target/policy combinations in one corpus invocation
  → upload raw result directories as a GitHub Actions artifact
  → publish job downloads that artifact
  → checkout gh-pages-rocjitsu, the source dashboard scripts and pinned corpus manifest
  → prepare-dashboard-data.py (once)
  → copy the run and catalog without overwriting existing files
  → update-dashboard-index.py
  → validate-dashboard-data.mjs
  → Git commit + push
```

- **Prepare:** pass the consolidated artifact's `run.json` once via `--raw-run`; validate per-result policy, identity, operation, samples and provenance; lowercase commit SHAs; preserve samples and derive medians only in normalized consumer data; and generate one maintained schema-1 run plus its suite-named catalog in an isolated build directory. Trusted `--corpus-dir`, repository-relative `--manifest` and `--expected-corpus-sha` inputs select committed TOML, not raw-artifact declarations. Each supplied raw input must independently match the full declared tuple set and typed workload definitions; diagnostic subsets reject even on first publication. Full finalized failures remain publishable. Preserve accepted sample order and corpus IDs. Failed/timeout wire rows retain partial samples and normalize to null duration. Policies remain literal `single`/`default` on configuration groups only; each group has `benchmark_results` with raw `id`, status, samples and error. Catalogs use `benchmark_suite`, ID-keyed `benchmark_definitions` and nested `membership[target][thread_policy]`. Problem/provenance values retain JSON types recursively. See [implementation status](schema-1.md#implementation-status) for implemented numeric rejection rules. Raw protocol lives in `execution_summary`. Four raw provenance sections retain typed facts, including explicit validated workflow_commit_sha in rocjitsu and tensile_commit_sha in auxiliary. Internal scalar environment projection preserves the earlier exclusions plus these tool revisions; it does not compare execution timestamps or the whole provenance object. The new-only wire shape still uses run schemaVersion1; old-shaped schema1 rejects and existing published resources must not be overwritten.
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
