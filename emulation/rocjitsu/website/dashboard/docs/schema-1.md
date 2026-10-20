# Schema 1 — maintained publication contract

This is the single maintained wire contract for new benchmark publications. The
preparer already emits version `1`, literal `single`/`default` policies and
nested `membership[target][thread_policy]` declarations. Version alone does **not** identify the retired
schema-1 target/plugin layout.

## Implementation status

The preparer and shared browser/CLI validation path now use this maintained shape:
required definitions, exact configuration membership, literal policies, recursive
typed problem values and required timing samples. Historical schemas are rejected,
not migrated or silently excluded. Bundled metadata requests schema 1.

This describes local implementation, not completed production rollout or real-runner
acceptance. Unsupported numeric values are rejected under the explicit conservative
bounds in [Supported numeric domain](#supported-numeric-domain), preventing unsafe
integer identity loss and oversized median arithmetic. No rounding or tolerance
is applied. The
already-parsed validation API cannot recover duplicate keys or original numeric
lexemes; use the shared strict text boundary for browser/CLI/processor loading.
No compatibility migration is promised.

## Files and metadata

Paths are relative to the dashboard or its publication data directory:

```text
src/config/metadata.json                 # bundled website settings, not fetched

data/
  index.json
  test-catalogs/<catalog-id>.json
  runs/default-branch/<run-id>.json       # source.branch == develop
  runs/side-branches/<run-id>.json         # all other branches, no branch subfolders
```

The target metadata specification is below. Changing bundled metadata alone is
not a consumer transition; it must accompany implementation of this contract.
Indexes and catalogs have no schema-version field.

```json
{
  "schemaVersion": 1,
  "repository": "https://github.com/ROCm/rocm-systems",
  "isBeta": true,
  "canonicalBranch": "develop"
}
```

## Complete fictional publication example

These are explanatory consumer fixtures, not real measurements or a producer
execution record. Catalog identity is the exact pinned manifest `name`, carried
by raw `execution_summary.benchmark_suite`, not a hash of observed results.
The illustrative suite below is named `example`.

### index.json

```json
{
  "generatedAt": "2026-10-01T12:00:00Z",
  "runFiles": [
    "runs/default-branch/run-001.json"
  ]
}
```

`generatedAt` is a strict ISO timestamp. `runFiles` contains unique, relative run
paths matching the layout above. An empty array is a valid empty publication.
Unindexed files are not loaded. A filename must match its run ID and branch
folder; run IDs are safe tokens containing letters, digits, `.`, `_` or `-`
(not `.` or `..`). Catalog references use `test-catalogs/<id>.json`; catalog ID
must match its filename. No absolute paths or traversal.

### test-catalogs/example.json

```json
{
  "benchmark_suite": "example",
  "benchmark_definitions": {
    "gemm": {
      "suite": "Example",
      "name": "GEMM",
      "operation": "Matrix multiplication",
      "problem": {
        "shape": [
          16,
          16,
          16
        ],
        "options": {
          "transpose": false
        },
        "note": null
      }
    }
  },
  "membership": {
    "gfx950": {
      "single": [
        "gemm"
      ],
      "default": [
        "gemm"
      ]
    }
  }
}
```

### runs/default-branch/run-001.json

```json
{
  "schemaVersion": 1,
  "id": "run-001",
  "benchmark_catalog": "test-catalogs/example.json",
  "source": {
    "branch": "develop",
    "message": "Fictional example"
  },
  "execution": {
    "trigger": "auto",
    "machine_label": "example-runner"
  },
  "execution_summary": {
    "benchmark_suite": "example",
    "timestamp": "2026-10-01T10:30:00Z",
    "finished_at": "2026-10-01T11:00:00Z",
    "wall_time_s": 1,
    "warmups": 0,
    "samples": 3,
    "timeout_seconds": 1200
  },
  "provenance": {
    "auxiliary": {
      "cores": 32,
      "tensile_commit_sha": "cccccccccccccccccccccccccccccccccccccccc"
    },
    "corpus": {
      "corpus_commit_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "corpus_commit_timestamp": "2026-10-01T09:00:00Z"
    },
    "machine": {
      "hostname": "fictional-host",
      "cpu": "fictional",
      "kernel": "fictional",
      "platform": "fictional"
    },
    "rocjitsu": {
      "rocjitsu_commit_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "rocjitsu_commit_timestamp": "2026-10-01T10:00:00Z",
      "rocm_sdk_version": null,
      "workflow_commit_sha": "dddddddddddddddddddddddddddddddddddddddd"
    }
  },
  "configurations": [
    {
      "target": "gfx950",
      "thread_policy": "single",
      "benchmark_results": [
        {
          "id": "gemm",
          "status": "completed",
          "timing_results_s": [
            1,
            9,
            2
          ],
          "error": null
        }
      ]
    },
    {
      "target": "gfx950",
      "thread_policy": "default",
      "benchmark_results": [
        {
          "id": "gemm",
          "status": "timeout",
          "timing_results_s": [
            5
          ],
          "error": "Execution timed out"
        }
      ]
    }
  ]
}
```

## Definitions and configuration membership

- Every definition is keyed by its exact raw `id` and requires nonempty `suite`, `name`, `operation` text and
  an object `problem` with nonempty property names. An empty problem object is
  allowed. Definition IDs are unique in a catalog.
- Corpus-owned IDs denote fixed definitions, independent of target, policy or
  recipe/catalog. Preserve IDs literally: no hashes, suffix removal or historical
  mapping. Distinct IDs remain distinct even with identical definitions. A reused
  ID must agree in suite, name, operation and typed problem across publications;
  incompatible definitions need a new ID, not a mandatory version suffix.
- Problem values retain original JSON types recursively: strings, finite numbers,
  booleans, null, arrays and objects. Object-key order is insignificant recursively;
  array order and value types are significant. `[1,2]` differs from `"[1,2]"`, and
  null differs from `"null"`. Display formatting must not mutate published values.
- Catalog `membership` is a nonempty target object containing nonempty policy objects (`single` or `default`). Each member array is nonempty, unique and references `benchmark_definitions` keys. No catalog id/schemaVersion or definition id aliases are accepted.
- Run configurations are unique target/policy groups and must equal catalog membership bidirectionally. Each `benchmark_results` array contains exactly one record per declared ID. An absent configuration is neither an empty group nor a zero measurement. Failure/timeout remains membership. `default` is automatic policy, not necessarily multithreaded.
- Reject duplicate JSON object keys rather than treating parser last-write-wins
  behavior as valid membership. The preparer's raw reader already checks this;
  other JSON entry points must not silently accept ambiguous declarations.

## Result rules

Every result requires only `id`, `status`, `timing_results_s`, `error`. Configuration owns target/policy. Result-level `thread_policy`, `testId`, `durationSeconds`, `exit_code` and repeated definitions reject.

Completed samples are nonempty, positive finite supported numbers and error is null. Failed/timeout samples may be empty or partial; error is null or nonempty text. Derive median once into internal durationSeconds for completed only; failed/timeout internal duration is null regardless of partial samples. Never reorder source samples. Even-count median averages the sorted middle pair. Source export contains NO derived duration.

## Source, execution and provenance

Run source contains branch and optional nonempty message, base and pullRequest; source commit/committedAt are rejected aliases. Source SHA/time live in `provenance.rocjitsu.rocjitsu_commit_sha` / `rocjitsu_commit_timestamp`. Required corpus SHA/time live in `provenance.corpus`. All commit facts are full lowercase40hex. Strict source/corpus commit times <= execution_summary.timestamp <= finished_at <= index.generatedAt. wall_time_s is nonnegative and not equated to clock subtraction or summed samples. Summary warmups is integer>=0, samples integer>=1 and timeout_seconds positive. execution owns auto/manual trigger and caller machine_label, distinct from raw machine hostname.

Four structured provenance sections auxiliary/corpus/machine/rocjitsu are required. Require raw hostname/platform/kernel/cpu and SDK string-or-null; preserve typed open facts recursively. Explicit validated workflow_commit_sha lives in rocjitsu, tensile_commit_sha in auxiliary; no guessed revisions. Both are required full40hex, remain in source export/display and are excluded from internal environment identity, as are source revision/time and target_config_sha256. Existing common protocol/runtime environment scalar projection is retained; no whole-provenance comparison identity.

Optional source.base has distinct branch and full commit; pullRequest requires base and positive safe number, optional credential-free HTTPS github.com URL ending in /pull/number without query/fragment. Missing fields stay absent. Separate attempt IDs remain unique even for the same tested commit.

Root/catalog/configuration/result envelopes reject unknown fields and old wire aliases. Open provenance section facts remain supported typed JSON. execution_summary.benchmark_suite must equal the referenced catalog benchmark_suite and filename; benchmark_catalog is the sole run reference. Index remains generatedAt/runFiles.

## Supported numeric domain

All numeric publication values must be finite with magnitude at most
`9007199254740991` (`Number.MAX_SAFE_INTEGER`). This applies recursively to
problem values and provenance/environment facts; booleans remain booleans.
Integer tokens outside this range reject, including decimal/exponent spellings.
Nonzero JSON tokens that underflow to zero also reject. Fractions use ordinary
binary64 semantics, not exact arbitrary-decimal semantics.

Timing samples and completed duration must be positive and no greater than
`4503599627370495`. This conservative ceiling keeps the existing even-median
addition within the safe boundary. Partial failed/timeout samples obey the same
ceiling; status and null-duration rules remain unchanged. Median equality remains
exact: no tolerance, rounding, coercion or clamping is introduced.

The producer rejects unsupported raw values before publication writes. Text loaders
check original numeric tokens before returning parsed values, so rounded invalid
input cannot reach export. Already-parsed object validation checks value bounds
but cannot recover lexemes or detect information lost before that API was called.
Accepted source export preserves parsed values, not arbitrary numeric precision.

## Rejection and export boundary

All supported maintained loaders must reject unversioned legacy input, old-shape
schema 1 (`targets`, plugin/comparison identity, environment wrappers, testCatalog, results/testId aliases), schema 2 (`threadingMode`, ST/MT,
colon keys), unsupported versions and malformed maintained data. Do not skip an
invalid historical record as if it were a valid maintained publication, fabricate
missing configurations or promise an upgrade path.

Dashboard JSON export preserves the parsed published `{index, catalogs, runs}`
fields/values through `sourceData`, regardless of filters, chart projections or
normalization. It is not byte-identical input JSON, a normalized chart export or
original runner `run.json`. Runner `exit_code`, stdout/stderr and other diagnostics
are separate workflow artifacts, not promised published export fields.

## Pinned declaration and completeness boundary

The preparer requires trusted `--corpus-dir`, `--manifest` and exact
`--expected-corpus-sha` inputs. It reads committed TOML bytes using Git, ignoring
working-tree changes. Every raw input must independently contain exactly the
manifest's full supported `(id, target, thread_policy)` matrix and matching typed
definitions. Missing/extra/duplicate cells, intentionally filtered first runs and
complementary subsets reject before writes. TOML parameters must be representable
under the maintained JSON/numeric rules; consumer JSON types remain unchanged.

A finalized full matrix may contain failures, timeouts and unexecuted failure
placeholders. These remain members, with null failed durations. Setup failure
before checkpoint and unfinished timestamps are not publishable. Timing, status,
error and sampling changes reuse the same catalog. Changed definitions or
membership require a new manifest name; incompatible workload definitions also
require new workload IDs. Existing named catalog paths are immutable.

This checks consistency with independently pinned declarations, including deletion
before catalog construction. It does not authenticate measurements, prove actual
native execution, or detect incorrectly authored manifests. Shared consumers
validate published identity/member agreement but do not independently fetch the
corpus. There is no registry, migration or partial-publication bypass.

See [preparing and publishing measurements](architecture-and-publication.md#preparing-and-publishing-measurements)
for generation and immutability, and [build/test commands](build-and-test.md).
