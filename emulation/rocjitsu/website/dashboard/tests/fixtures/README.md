# Fictional maintained-schema dashboard fixtures

Every measurement, branch, machine and commit message here is **fictional test
input**, not a published Rocjitsu performance claim. Never publish this directory.
Production builds do not import the generators or copy fixture JSON.

## Deterministic publication

`maintainedDataset.js` generates 24 develop attempts and 20 fictional side branches.
Each run declares `schemaVersion: 1`, a `benchmark_catalog` reference, caller
`source`/`execution`, original-named `execution_summary` and four structured
`provenance` sections. Source/corpus/workflow/Tensile fixture hashes are explicitly
fictional valid full40hex values. Configuration groups own the literal
`thread_policy: single/default`; their `benchmark_results` contain only raw `id`,
status, ordered `timing_results_s` and error. Wire records contain no derived
`durationSeconds` or repeated policy/definitions. The consumer derives completed
medians internally and uses internal null duration for failed/timeout records,
even when partial samples are present.

Catalogs use `benchmark_suite`, exact ID-keyed `benchmark_definitions` retaining
suite/name/operation/typed problem, and nested `membership[target][thread_policy]`
that agrees exactly with run groups/results. Sparse attempts have separate
equally sparse catalogs, rather than omitting a run group against a fully declared
catalog. Indexes/catalogs have no version field. No legacy wire aliases or
migration adapters are provided.

The base old/current catalogs exercise deleted/added workloads; dedicated variants
exercise configuration absence. Tests retain chronology, late execution/backfill,
independent machines/environments, failure/timeout, per-policy scope and exact
branch/base/PR provenance. Explicit zero-baseline arithmetic remains isolated
normalized test input; zero is not a valid maintained completed publication.
Overview uses configuration-specific range-wide cohorts, not legacy anchors.
The checked-in default is a broad browser baseline; focused contract scenarios
also exercise the maintained publication boundary rather than only normalized data.

`createFeedbackPublication()` adds `users/RattataKing/test-branch` without renaming
other branches. The complete static publication has 24 develop attempts and 21
branches. `publishedData.js` re-exports that test-only overlay. The base builder
and `writeMaintainedFixtureDirectory()` remain base-only APIs.

Regenerate the complete checked-in test publication:

```bash
node tests/fixtures/regenerate-fixtures.js
```

The command validates before writing, clears its destination, and defaults to
`tests/fixtures/data/`. An optional directory argument allows scratch regeneration.
Never point a fixture writer at production data. The test-only
`setFixtureConfigurations()` helper creates coherent catalog variants when a
positive test changes configuration scope; production validation never repairs
malformed membership this way.

`syntheticDataset.js` separately generates the 500-attempt queue/concurrency case
in memory. It is not copied into browser fixtures. In `fixtures` mode, the App
loads run/catalog bodies with `no-store` because local fixture files change at
stable URLs. This bypasses retained old-schema HTTP bodies without clearing
browser storage. A normal page reload picks up updated fixture-mode code/data;
production publications keep immutable `force-cache` behavior. Explicit Reload
all data still refreshes bodies and uses its existing cache-generation token.
Loader tests retain cache
policy/generation, progress, retry/Retry-After, timeout/cancellation and resource
failure coverage. A strict shared text boundary rejects duplicate decoded JSON
keys; every consumer rejects legacy/unversioned/schema-2 shapes rather than
migrating or silently skipping instrumented inputs. Parsed `sourceData` preserves
published fields and values independently of selection/filtering.

## Focused Overview contract publication

Generate a separate fictional publication into an explicit disposable directory:

```bash
node tests/fixtures/regenerate-fixtures.js /path/to/disposable-data --overview-contract
```

This does not replace the default 45-run browser baseline. The seven develop
attempts use three catalog periods, nested JSON-typed definitions, both targets
and policies, an absent configuration and a missing day. Three attempts share
one commit: two complete attempts remain separately eligible in 1W; a later
failed required member is excluded only when its lane/family participates.
Daily views keep that failure rather than falling back. A disjoint per-policy
intersection stays unavailable, not zero. Regeneration tests validate actual
wire files, export/source preservation, cohorts and empty/filter outcomes.

The writer clears its destination. Never use published data or a directory owned
by a running server; use the default generator without this option for the
checked-in broad baseline.

## Local consumer tools

```bash
node scripts/validate-dashboard-data.mjs <data-directory>
node scripts/process-dashboard-data.mjs <data-directory> --output <new-file-outside-input>
```

Processing validates before writing, refuses output inside the input directory or
an existing output file, and emits `{data,sourceData}`. Only `backfillRunIds`
changes representation to a JSON array. Normalized `data` is inspection output,
not a supported dashboard re-import format. Without `--output`, processing prints
JSON to stdout. These tools do not publish or fabricate benchmark measurements.
See the [maintained contract](../../docs/schema-1.md), including its explicit
supported numeric domain; fictional fixture success is not real-runner acceptance.
