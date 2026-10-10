# Copyright (c) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: MIT
"""Static contract for the benchmark dashboard publication orchestration."""

from pathlib import Path

WORKFLOW = (
    Path(__file__).resolve().parents[7] / '.github/workflows/rocjitsu-benchmarks.yml'
)


def test_benchmark_uses_one_consolidated_multi_policy_run():
    text = WORKFLOW.read_text(encoding='utf-8')
    benchmark = text.split('      - name: Run performance suite', 1)[1].split(
        '      - name: Upload benchmark diagnostics', 1
    )[0]
    assert benchmark.count('-m benchmarks.runner') == 1
    assert '--manifest benchmarks/suites/performance-v1.toml' in benchmark
    assert '--thread-policy default,single' in benchmark
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
    assert publish.index('validate-dashboard-data.mjs') < publish.index('git commit')


def test_publication_workflow_is_short_safe_orchestration():
    text = WORKFLOW.read_text(encoding='utf-8')
    publish = text.split('\n  publish:', 1)[1]

    assert 'path: publication\n          ref: ${{ env.RESULTS_BRANCH }}' in publish
    assert publish.count('prepare-dashboard-data.py') == 1
    assert 'runs/default-branch/${RUN_ID}.json' in publish
    assert 'runs/side-branches/${RUN_ID}.json' in publish
    assert 'CATALOGS=("${BUILD_DIR}"/test-catalogs/*.json)' in publish
    assert '${#CATALOGS[@]} -ne 1' in publish
    assert publish.count('cp -n ') == 2
    assert publish.count('cmp -s ') == 2
    symlink_check = publish.index('for PATH_COMPONENT in')
    assert '-L "${PATH_COMPONENT}"' in publish
    assert symlink_check < publish.index('cp -n ')
    assert 'update-dashboard-index.py' in publish
    assert 'validate-dashboard-data.mjs' in publish
    assert publish.count('git add ') == 1
    for path in (
        '"rocjitsu-dashboard/data/index.json"',
        '"rocjitsu-dashboard/data/${RUN_PATH}"',
        '"rocjitsu-dashboard/data/${CATALOG_PATH}"',
    ):
        assert path in publish
    assert publish.count('git push ') == 1

    prohibited = (
        'publish-' + 'dashboard-run.py',
        'MAX_ATTEMPTS',
        'for ATTEMPT',
        'git fetch',
        'git reset',
        'git switch --orphan',
        'force-with-lease',
        'rm -rf',
        'rm -fr',
        'rm -r',
        'rm -R',
        'rm --recursive',
        'git rm -rf',
        'git rm -r',
        'git rm -R',
        'dashboard-tests-venv',
    )
    for value in prohibited:
        assert value not in publish
