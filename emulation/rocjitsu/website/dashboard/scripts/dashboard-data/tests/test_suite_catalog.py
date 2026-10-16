# Copyright (c) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: MIT
"""Pinned declaration boundary; all measurements are fictional, never native proof."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'prepare-dashboard-data.py'
spec = importlib.util.spec_from_file_location('suite_preparer', SCRIPT)
assert spec is not None and spec.loader is not None
producer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(producer)

MANIFEST = '''name = "Suite.v1"
[[cases]]
id = "a"
suite = "Triton"
name = "Example"
operation = "Compute"
targets = ["gfx950", "gfx1250"]
thread_policies = ["default", "single"]
params = {shape = [1, 2], flag = true}
'''


def committed_manifest(root, content=MANIFEST):
    root.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()
    git('init', '-q')
    file = root / 'suite.toml'
    file.write_text(content)
    git('add', 'suite.toml')
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        '-c', 'commit.gpgsign=false', 'commit', '--no-gpg-sign', '--no-signoff', '-qm', 'Declare fictional suite')
    return git('rev-parse', 'HEAD')


def rows():
    return [{'id': 'a', 'suite': 'Triton', 'name': 'Example', 'operation': 'Compute',
             'problem': {'shape': [1, 2], 'flag': True}, 'target': target, 'thread_policy': policy}
            for target in ('gfx950', 'gfx1250') for policy in ('default', 'single')]


def test_pinned_full_matrix_identity_and_dirty_worktree(tmp_path):
    repo = tmp_path / 'corpus'
    sha = committed_manifest(repo)
    declaration = producer.load_pinned_manifest(repo, 'suite.toml', sha)
    (repo / 'suite.toml').write_text('name = "forged"')
    assert producer.load_pinned_manifest(repo, 'suite.toml', sha) == declaration
    producer.validate_manifest_run({'execution_summary': {'benchmark_suite': 'Suite.v1'}, 'benchmark_results': rows()}, declaration)
    assert declaration['name'] == 'Suite.v1'


@pytest.mark.parametrize('change,category', [
    ('missing', 'missing'), ('extra', 'extra'), ('duplicate', 'Duplicate'),
    ('definition', 'definition'), ('typed', 'definition'), ('suite', 'benchmark_suite'),
])
def test_pinned_matrix_counterexamples_reject(tmp_path, change, category):
    repo = tmp_path / 'corpus'
    sha = committed_manifest(repo)
    declaration = producer.load_pinned_manifest(repo, 'suite.toml', sha)
    raw = {'execution_summary': {'benchmark_suite': 'Suite.v1'}, 'benchmark_results': rows()}
    if change == 'missing': raw['benchmark_results'].pop()
    if change == 'extra': raw['benchmark_results'][0]['target'] = 'gfx999'
    if change == 'duplicate': raw['benchmark_results'].append(copy.deepcopy(raw['benchmark_results'][0]))
    if change == 'definition': raw['benchmark_results'][0]['problem']['shape'].reverse()
    if change == 'typed': raw['benchmark_results'][0]['problem']['flag'] = 1
    if change == 'suite': raw['execution_summary']['benchmark_suite'] = 'Other'
    with pytest.raises(ValueError, match=category):
        producer.validate_manifest_run(raw, declaration)


@pytest.mark.parametrize('path', ['', '/suite.toml', '../suite.toml', './suite.toml', 'a//b', 'a\\b', 'a/../b', 'a/\x00b'])
def test_manifest_paths_are_literal_and_safe(tmp_path, path):
    with pytest.raises(ValueError, match='manifest'):
        producer.load_pinned_manifest(tmp_path, path, 'a' * 40)


@pytest.mark.parametrize('kind', ['missing-commit', 'blob-not-commit', 'missing-blob', 'malformed', 'duplicate-support', 'duplicate-id', 'datetime-param', 'unsafe-name'])
def test_pinned_source_failures_are_closed(tmp_path, kind):
    repo = tmp_path / 'corpus'
    content = MANIFEST
    if kind == 'malformed': content = 'not valid TOML ['
    if kind == 'duplicate-support': content = content.replace('["default", "single"]', '["default", "default"]')
    if kind == 'duplicate-id': content += '\n[[cases]]' + content.split('[[cases]]', 1)[1]
    if kind == 'datetime-param': content = content.replace('flag = true', 'flag = 2026-01-01')
    if kind == 'unsafe-name': content = content.replace('Suite.v1', '../escape')
    sha = committed_manifest(repo, content)
    manifest = 'suite.toml'
    if kind == 'missing-commit': sha = 'f' * 40
    if kind == 'blob-not-commit': sha = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD:suite.toml'], text=True).strip()
    if kind == 'missing-blob': manifest = 'absent.toml'
    with pytest.raises((ValueError, TypeError)):
        producer.load_pinned_manifest(repo, manifest, sha)
