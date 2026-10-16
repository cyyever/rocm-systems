# Copyright (c) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: MIT
"""Explicit fictional committed declarations for producer/concurrency fixtures.

This helper is not the production completeness oracle. Source-boundary negative
cases must commit their unchanged expected manifest BEFORE mutating raw rows.
"""
import hashlib
import json
from pathlib import Path
import subprocess


def toml_value(value):
    if isinstance(value, dict):
        return '{' + ', '.join(f'{json.dumps(key)} = {toml_value(value[key])}' for key in sorted(value)) + '}'
    if isinstance(value, list):
        return '[' + ', '.join(toml_value(item) for item in value) + ']'
    if value is None:
        raise ValueError('TOML source declarations cannot contain null')
    return json.dumps(value)


def declare_fixture(root, inputs):
    """Declare a fictional suite from positive test specifications, not execution."""
    cases = {}
    for raw in inputs:
        for row in raw['benchmark_results']:
            if not isinstance(row.get('target'), str) or not isinstance(row.get('thread_policy'), str):
                continue
            case = cases.setdefault(row['id'], {**row, 'targets': [], 'thread_policies': []})
            for source, dest in [('target', 'targets'), ('thread_policy', 'thread_policies')]:
                if row[source] not in case[dest]: case[dest].append(row[source])
    lines = ['name = ' + json.dumps(inputs[0]['execution_summary']['benchmark_suite'])]
    for case in sorted(cases.values(), key=lambda c: c['id']):
        lines.append('[[cases]]')
        for key in ('id', 'suite', 'name', 'operation', 'targets', 'thread_policies'):
            value = sorted(case[key]) if key in ('targets', 'thread_policies') else case.get(key, 'Fixture')
            lines.append(f'{key} = {toml_value(value)}')
        lines.append('params = ' + toml_value(case.get('problem', {})))
    content = '\n'.join(lines) + '\n'
    repository = Path(root) / ('declared-' + hashlib.sha256(content.encode()).hexdigest())
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repository), *args], text=True).strip()
    if not repository.exists():
        repository.mkdir()
        git('init', '-q')
        (repository / 'suite.toml').write_text(content)
        git('add', 'suite.toml')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
            '-c', 'commit.gpgsign=false', 'commit', '--no-gpg-sign', '--no-signoff', '-qm', 'Declare fictional suite')
    return repository, git('rev-parse', 'HEAD')
