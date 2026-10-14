# Fictional maintained-schema dashboard fixtures

Every measurement, branch, machine and commit message here is **fictional test
input**, not a published Rocjitsu performance claim. Never publish this directory.
Production builds do not import the generators or copy fixture JSON.

## Deterministic publication

`maintainedDataset.js` generates 24 develop attempts and 20 fictional side branches.
Each run declares `schemaVersion: 1`, literal `thread_policy: single/default`,
ordered timing samples and positive completed median duration. Failed/timeout
records have null duration. Definitions require operation metadata. Catalog
configuration keys are `target/policy` and agree exactly with their run groups.
Sparse attempts have separate equally sparse catalogs, rather than omitting a
run group against a fully declared catalog. Indexes/catalogs have no version field.

The base old/current catalogs exercise deleted/added workloads; dedicated variants
exercise configuration absence. Tests retain chronology, late execution/backfill,
independent machines/environments, failure/timeout, per-policy scope and exact
branch/base/PR provenance. Explicit zero-baseline arithmetic remains isolated
normalized test input; zero is not a valid maintained completed publication.
Overview's legacy anchor algorithm remains tested until its separate replacement
stage; schema compatibility is not acceptance of that comparison algorithm.

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
in memory. It is not copied into browser fixtures. Loader tests retain cache
policy/generation, progress, retry/Retry-After, timeout/cancellation and resource
failure coverage. A strict shared text boundary rejects duplicate decoded JSON
keys; every consumer rejects legacy/unversioned/schema-2 shapes rather than
migrating or silently skipping instrumented inputs. Parsed `sourceData` preserves
published fields and values independently of selection/filtering.

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
See the [maintained contract](../../docs/schema-1.md), including its unresolved
numeric precision gate; fictional fixture success is not real-runner acceptance.
