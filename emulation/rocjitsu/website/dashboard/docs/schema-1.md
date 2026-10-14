# Schema 1 — maintained publication contract

This is the single maintained wire contract for new benchmark publications. The
preparer already emits version `1`, literal `single`/`default` policies and
`target/policy` membership keys. Version alone does **not** identify the retired
schema-1 target/plugin layout.

## Implementation status

The preparer and shared browser/CLI validation path now use this maintained shape:
required definitions, exact configuration membership, literal policies, recursive
typed problem values and required timing samples. Historical schemas are rejected,
not migrated or silently excluded. Bundled metadata requests schema 1.

This describes local implementation, not completed production rollout or real-runner
acceptance. Numeric precision remains an unresolved publication gate: an unbounded
Python integer can lose precision when parsed as a JavaScript number (for example,
`9007199254740993` becomes `9007199254740992`), and cross-runtime even-sample medians
can disagree. No rounding, tolerance or integer bound is silently imposed here;
those semantics require an explicit contract decision before acceptance. The
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

These are explanatory fixtures, not real measurements. The illustrative catalog
ID is filename-safe; production catalog IDs are content-addressed by the preparer.

### index.json

```json
{
  "generatedAt": "2026-10-01T12:00:00Z",
  "runFiles": ["runs/default-branch/run-001.json"]
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
  "id": "example",
  "tests": [
    {
      "id": "gemm",
      "suite": "Example",
      "name": "GEMM",
      "operation": "Matrix multiplication",
      "problem": {"shape": [16, 16, 16], "options": {"transpose": false}, "note": null}
    }
  ],
  "configurations": {
    "gfx950/single": ["gemm"],
    "gfx950/default": ["gemm"]
  }
}
```

### runs/default-branch/run-001.json

```json
{
  "schemaVersion": 1,
  "id": "run-001",
  "testCatalog": "test-catalogs/example.json",
  "source": {
    "branch": "develop",
    "commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "committedAt": "2026-10-01T10:00:00Z",
    "message": "Fictional example"
  },
  "execution": {
    "completedAt": "2026-10-01T11:00:00Z",
    "trigger": "auto",
    "machine": "example-runner"
  },
  "environment": [{"key": "cores", "label": "CPU cores", "value": 32}],
  "configurations": [
    {
      "target": "gfx950",
      "thread_policy": "single",
      "results": [
        {"testId": "gemm", "thread_policy": "single", "status": "completed", "timing_results_s": [1, 9, 2], "durationSeconds": 2, "error": null}
      ]
    },
    {
      "target": "gfx950",
      "thread_policy": "default",
      "results": [
        {"testId": "gemm", "thread_policy": "default", "status": "timeout", "timing_results_s": [5], "durationSeconds": null, "error": "Execution timed out"}
      ]
    }
  ]
}
```

## Definitions and configuration membership

- Every definition requires nonempty `id`, `suite`, `name`, `operation` text and
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
- Catalog `configurations` is a nonempty object. Keys are `target/policy`, with a
  filename-safe target token and literal policy `single` or `default`. `default`
  means automatic/default policy, not necessarily multithreaded execution.
- Each membership array is nonempty, contains unique IDs and references catalog
  definitions. Run configuration groups are nonempty and unique by target/policy.
  Their key set must equal the catalog key set **bidirectionally**. Neither a
  catalog-only declaration nor a run-only group is allowed.
- Each group contains exactly one result per declared member, no duplicates,
  missing or extra IDs. Each result's `thread_policy` equals its group policy.
  An absent configuration has neither a catalog key nor a run group; it is not
  an empty group or a zero measurement. Failures/timeouts remain members.
- Reject duplicate JSON object keys rather than treating parser last-write-wins
  behavior as valid membership. The preparer's raw reader already checks this;
  other JSON entry points must not silently accept ambiguous declarations.

## Result rules

Every result requires `testId`, `thread_policy`, `status`, `timing_results_s`,
`durationSeconds` and `error`.

| Status | Samples | Duration | Error |
| --- | --- | --- | --- |
| `completed` | Nonempty positive finite numeric array | Published median of samples, positive and finite | null |
| `failed` | Empty or partial positive finite numeric array | null | null or nonempty text |
| `timeout` | Empty or partial positive finite numeric array | null | null or nonempty text |

Sample order/values are preserved, not reconstructed from the median. Median
uses sorted samples and averages the middle pair for an even count. Partial
samples never turn failure into success. Unsupported statuses, nonfinite numbers,
missing required fields and duration/sample mismatches reject.

## Source, execution and environment

Source branch is nonempty text; commit/base SHAs are lowercase 40-hex strings.
`source.committedAt`, `execution.completedAt` and index publication time are strict
ISO timestamps with timezone and valid calendar/time components. Commit ≤
completion ≤ publication. Trigger is `auto` or `manual`; machine is nonempty text.
`source.message` is optional nonempty text (the preparer emits it).

Side-branch provenance may include `source.base: {branch, commit}` and
`source.pullRequest: {number, url?}`. Base branch is nonempty and differs from the
source branch; PR number is a positive integer and requires a source base. An
optional PR URL is credential-free HTTPS on github.com, ends in `/pull/<number>`,
and has no query/fragment. The workflow omits base/PR fields for develop runs.

`environment` is an array of unique-key `{key, label, value}` facts: key/label are
nonempty text and value is a string, boolean or finite number. This scalar fact
format is separate from recursively typed workload `problem` values. Preparation
records shared protocol facts `execution.warmups`, `execution.samples`,
`execution.timeout_seconds`, `execution.benchmark_suite`, without policy prefixes
or target config hashes; source revision/time lives in `source`.

## Rejection and export boundary

All supported maintained loaders must reject unversioned legacy input, old-shape
schema 1 (`targets`, plugin/comparison identity), schema 2 (`threadingMode`, ST/MT,
colon keys), unsupported versions and malformed maintained data. Do not skip an
invalid historical record as if it were a valid maintained publication, fabricate
missing configurations or promise an upgrade path.

Dashboard JSON export preserves the parsed published `{index, catalogs, runs}`
fields/values through `sourceData`, regardless of filters, chart projections or
normalization. It is not byte-identical input JSON, a normalized chart export or
original runner `run.json`. Runner `exit_code`, stdout/stderr and other diagnostics
are separate workflow artifacts, not promised published export fields.

## Output-derived membership boundary

Catalog membership is derived from recorded runner results, not a separate matrix
registry. After its first checkpoint, the runner retains selected unexecuted cells
as failed placeholders. Setup failure before that checkpoint has no publishable
run. Deleting a result while retaining catalog membership is malformed and must
reject. Deleting a cell **before catalog generation**, or constructing the wrong
matrix, can evade intended-membership detection; equality validation cannot prove
the intended matrix was executed. No new registry/status inventory is in scope.

See [preparing and publishing measurements](architecture-and-publication.md#preparing-and-publishing-measurements)
for generation and immutability, and [build/test commands](build-and-test.md).
