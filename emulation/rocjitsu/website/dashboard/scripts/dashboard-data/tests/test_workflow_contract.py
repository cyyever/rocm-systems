# Copyright (c) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: MIT
"""Static contract for the benchmark dashboard publication orchestration."""

from pathlib import Path

WORKFLOW = (
    Path(__file__).resolve().parents[7] / '.github/workflows/rocjitsu-benchmarks.yml'
)


def test_benchmark_pairs_unfiltered_caller_with_compatible_pin():
    text = WORKFLOW.read_text(encoding='utf-8')
    assert '  CORPUS_SHA: e191fc247b8c04f984f41cf2b2a83ff89d6a0854\n' in text
    assert '          ref: ${{ env.CORPUS_SHA }}\n' in text


def test_benchmark_uses_one_consolidated_multi_policy_run():
    text = WORKFLOW.read_text(encoding='utf-8')
    benchmark = text.split('      - name: Run performance suite', 1)[1].split(
        '      - name: Upload benchmark diagnostics', 1
    )[0]
    assert benchmark.count('-m benchmarks.runner') == 1
    assert benchmark.count('--manifest ') == 1
    assert '--manifest benchmarks/suites/performance-v1.toml' in benchmark
    for selector in ('--thread-policy', '--target ', '--case ', '--warmups', '--samples'):
        assert selector not in benchmark
    assert benchmark.count('--target-config ') == 2
    assert '--run-wrapper "\\\"${ROCJITSU_BUILD_DIR}/tools/rocjitsu/rocjitsu\\\" --config {config} --"' in benchmark
    assert '--cpu-thread-budget' not in benchmark
    assert '--output "${ROCJITSU_RESULT_DIR}"' in benchmark
    assert '--target-config "gfx950=' in benchmark
    assert '--target-config "gfx1250=' in benchmark
    assert text.count('--raw-run ') == 1
    assert '--raw-run "${RESULTS_DOWNLOAD_DIR}/run.json"' in text
    for removed in (
        'SINGLE_THREAD_MODE',
        'MULTI_THREAD_MODE',
        'nightly.toml',
        'nightly-single.toml',
        'for MODE',
    ):
        assert removed not in text
    publish = text.split('\n  publish:', 1)[1]
    helper = (WORKFLOW.parents[2] / 'emulation/rocjitsu/website/dashboard/scripts/dashboard-data/publish-dashboard-run.sh').read_text()
    assert helper.index('validate-dashboard-data.mjs') < helper.index('git commit')


def test_workflow_records_checked_tool_revisions_and_passes_them_to_preparer():
    text = WORKFLOW.read_text(encoding='utf-8')
    benchmark = text.split('\n  benchmark:', 1)[1].split('\n  publish:', 1)[0]
    assert 'workflow_commit_sha: ${{ steps.source.outputs.workflow_commit_sha }}' in benchmark
    assert 'tensile_commit_sha: ${{ steps.tensile.outputs.commit_sha }}' in benchmark
    assert 'git rev-parse --verify HEAD^{commit}' in benchmark
    assert 'git -C "${TENSILE_SOURCE}" rev-parse --verify HEAD^{commit}' in benchmark
    publish = text.split('\n  publish:', 1)[1]
    assert '--workflow-commit-sha "${WORKFLOW_COMMIT_SHA}"' in publish
    assert '--tensile-commit-sha "${TENSILE_COMMIT_SHA}"' in publish
    assert 'WORKFLOW_COMMIT_SHA: ${{ needs.benchmark.outputs.workflow_commit_sha }}' in publish
    assert 'TENSILE_COMMIT_SHA: ${{ needs.benchmark.outputs.tensile_commit_sha }}' in publish
    assert 'benchmark_catalog' in publish
    assert 'benchmark_suite' in publish


def test_publication_workflow_is_short_safe_orchestration():
    text = WORKFLOW.read_text(encoding='utf-8')
    publish = text.split('\n  publish:', 1)[1]
    checkout = publish.split('      - name: Checkout pinned publication manifest', 1)[1].split('      - name: Set up publisher Python', 1)[0]
    assert 'repository: ROCm/rocjitsu-test-corpus' in checkout
    assert 'ref: ${{ env.CORPUS_SHA }}' in checkout
    assert 'persist-credentials: false' in checkout
    assert 'path: publication-corpus' in checkout
    assert 'sparse-checkout: benchmarks/suites' in checkout
    assert '--corpus-dir "${GITHUB_WORKSPACE}/publication-corpus"' in publish
    assert '--manifest benchmarks/suites/performance-v1.toml' in publish

    assert 'path: publication\n          ref: ${{ env.RESULTS_BRANCH }}' in publish
    assert publish.count('prepare-dashboard-data.py') == 1
    assert 'runs/default-branch/${RUN_ID}.json' in publish
    assert 'runs/side-branches/${RUN_ID}.json' in publish
    assert 'CATALOGS=("${BUILD_DIR}"/test-catalogs/*.json)' in publish
    assert '${#CATALOGS[@]} -ne 1' in publish
    assert publish.count('publish-dashboard-run.sh') == 1
    assert '"${BUILD_DIR}" "${RUN_PATH}" "${CATALOG_PATH}" "${RESULTS_BRANCH}"' in publish
    helper = (WORKFLOW.parents[2] / 'emulation/rocjitsu/website/dashboard/scripts/dashboard-data/publish-dashboard-run.sh').read_text()
    assert 'for ATTEMPT in 1 2 3; do' in helper
    assert helper.count('git push ') == 1
    assert 'git push --porcelain origin "HEAD:refs/heads/${RESULTS_BRANCH}"' in helper
    assert 'git fetch --no-tags origin "refs/heads/${RESULTS_BRANCH}"' in helper
    assert 'git reset --hard FETCH_HEAD' in helper
    assert helper.index('for PATH_COMPONENT in') < helper.index('cp "${BUILD_DIR}')
    assert '-L "${PATH_COMPONENT}"' in helper
    assert 'cmp -s ' in helper
    assert helper.index('update-dashboard-index.py') < helper.index('validate-dashboard-data.mjs')
    assert helper.index('validate-dashboard-data.mjs') < helper.index('git commit')
    assert helper.index('git commit') < helper.index('git push')
    for path in ('"rocjitsu-dashboard/data/index.json"',
                 '"rocjitsu-dashboard/data/${RUN_PATH}"',
                 '"rocjitsu-dashboard/data/${CATALOG_PATH}"'):
        assert path in helper
    diagnostics = publish.split('      - name: Upload publication diagnostics', 1)[1]
    assert 'if: always()' in diagnostics
    assert 'retention-days: 14' in diagnostics
    for prohibited in ('--force', 'force-with-lease', 'git switch --orphan', 'rm -rf', 'benchmarks.runner'):
        assert prohibited not in helper
