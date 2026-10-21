# Copyright (c) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: MIT
"""Workflow wiring and shell syntax; publication behavior runs in local Git tests."""

from pathlib import Path
import subprocess

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[7] / '.github/workflows'


def test_publication_steps_follow_responsibility_order():
    workflow = yaml.safe_load((WORKFLOWS / 'rocjitsu-benchmarks.yml').read_text())
    assert [step['name'] for step in workflow['jobs']['publish']['steps']] == [
        'Download benchmark diagnostics', 'Checkout repository for publication',
        'Fill publication metadata', 'Store immutable run', 'Update run index',
        'Commit and push publication', 'Upload publication diagnostics',
    ]


def test_diagnostics_path_uses_runtime_context_and_upload_survives_early_failure():
    workflow = yaml.safe_load((WORKFLOWS / 'rocjitsu-benchmarks.yml').read_text())
    publish = workflow['jobs']['publish']
    # runner is unavailable in job env, but available in a step's with values.
    assert 'DIAGNOSTICS_DIR' not in publish['env']
    fill = next(s for s in publish['steps'] if s['name'] == 'Fill publication metadata')
    assert 'DIAGNOSTICS_DIR="${RUNNER_TEMP}/dashboard-publication-diagnostics"' in fill['run']
    assert 'DIAGNOSTICS_DIR=%s' in fill['run'] and '"${GITHUB_ENV}"' in fill['run']
    upload = next(s for s in publish['steps'] if s['name'] == 'Upload publication diagnostics')
    assert upload['if'] == 'always()'
    assert upload['with']['path'] == '${{ runner.temp }}/dashboard-publication-diagnostics'


def test_benchmark_pin_and_unfiltered_execution():
    workflow = yaml.safe_load((WORKFLOWS / 'rocjitsu-benchmarks.yml').read_text())
    assert workflow['env']['CORPUS_SHA'] == 'b95ea549e1f500ce4ce83ae511ae5e4434930374'
    benchmark = workflow['jobs']['benchmark']
    command = next(s['run'] for s in benchmark['steps'] if s['name'] == 'Run performance suite')
    assert command.count('-m benchmarks.runner') == 1
    assert '--manifest benchmarks/suites/performance-v1.toml' in command
    assert command.count('--target-config ') == 2
    assert '--output "${ROCJITSU_RESULT_DIR}"' in command
    for selector in ('--thread-policy', '--target ', '--case ', '--warmups', '--samples'):
        assert selector not in command


def test_publication_metadata_uses_existing_checked_outputs():
    workflow = yaml.safe_load((WORKFLOWS / 'rocjitsu-benchmarks.yml').read_text())
    benchmark = workflow['jobs']['benchmark']
    assert benchmark['outputs']['workflow_commit_sha'] == '${{ steps.source.outputs.workflow_commit_sha }}'
    assert benchmark['outputs']['tensile_commit_sha'] == '${{ steps.tensile.outputs.commit_sha }}'
    publish = workflow['jobs']['publish']
    assert publish['env']['WORKFLOW_COMMIT_SHA'] == '${{ needs.benchmark.outputs.workflow_commit_sha }}'
    assert publish['env']['TENSILE_COMMIT_SHA'] == '${{ needs.benchmark.outputs.tensile_commit_sha }}'
    assert publish['env']['BENCHMARK_COMMIT_MESSAGE'] == '${{ needs.benchmark.outputs.source_commit_message }}'
    for field in ('base_branch', 'base_sha', 'pull_request_number', 'pull_request_url'):
        assert '${{ needs.source-metadata.outputs.' + field + ' }}' in publish['env'].values()


def test_manual_publication_guard_and_diagnostics_remain_independent():
    workflow = yaml.safe_load((WORKFLOWS / 'rocjitsu-benchmarks.yml').read_text())
    condition = workflow['jobs']['publish']['if']
    assert "!cancelled() && needs.benchmark.outputs.ran == 'true'" in condition
    assert "github.event_name != 'workflow_dispatch' || inputs.publish_results == true" in condition
    for job, name in [('benchmark', 'Upload benchmark diagnostics'), ('publish', 'Upload publication diagnostics')]:
        step = next(s for s in workflow['jobs'][job]['steps'] if s['name'] == name)
        assert step['if'] == 'always()'
        assert step['with']['retention-days'] == 14


@pytest.mark.parametrize('name', ['rocjitsu-benchmarks.yml', 'rocjitsu-website-test.yml',
                                   'rocjitsu-publish-website.yml'])
def test_workflow_yaml_and_bash_syntax(name):
    workflow = yaml.safe_load((WORKFLOWS / name).read_text())
    count = 0
    for job in workflow['jobs'].values():
        for step in job['steps']:
            if 'run' not in step:
                continue
            result = subprocess.run(['bash', '-n'], input=step['run'], capture_output=True, text=True)
            assert result.returncode == 0, f"{name}: {step['name']}: {result.stderr}"
            count += 1
    assert count > 0
