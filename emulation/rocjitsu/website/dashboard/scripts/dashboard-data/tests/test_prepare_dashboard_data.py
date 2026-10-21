#!/usr/bin/env python3
# Copyright (c) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: MIT
"""Producer integration tests; all measurements are fictional fixtures."""

import copy
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
import importlib.util
import math
import runpy
from unittest.mock import patch
import pytest
from manifest_fixture import declare_fixture

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / 'prepare-dashboard-data.py'
UPDATE = HERE.parent / 'update-dashboard-index.py'
SHA = 'a' * 40
CORPUS = 'b' * 40


def raw(policy='single'):
    return {
        'execution_summary': {
            'warmups': 1,
            'samples': 3,
            'timeout_seconds': 60,
            'benchmark_suite': 'smoke',
            'timestamp': '2026-01-01T01:00:00Z',
            'finished_at': '2026-01-01T01:01:00Z',
            'wall_time_s': 60,
        },
        'benchmark_results': [
            {
                'id': 'case-1',
                'name': 'Example',
                'target': 'gfx950',
                'suite': 'smoke',
                'operation': 'Example computation',
                'thread_policy': policy,
                'problem': {'size': 8},
                'status': 'completed',
                'exit_code': 0,
                'error': None,
                'timing_results_s': [1, 9, 2],
            }
        ],
        'provenance': {
            'machine': {
                'hostname': 'worker',
                'platform': 'Linux',
                'kernel': '6.8',
                'cpu': 'Example CPU',
            },
            'rocjitsu': {
                'rocjitsu_commit_sha': SHA,
                'rocjitsu_commit_timestamp': '2026-01-01T00:00:00Z',
                'rocm_sdk_version': '7.0',
            },
            'corpus': {
                'corpus_commit_sha': CORPUS,
                'corpus_commit_timestamp': '2025-12-01T00:00:00Z',
            },
            'auxiliary': {},
        },
    }


def consolidated(*inputs):
    from datetime import datetime
    value = copy.deepcopy(inputs[0])
    value['benchmark_results'] = [copy.deepcopy(row) for raw_input in inputs for row in raw_input['benchmark_results']]
    value['execution_summary']['finished_at'] = max(
        (item['execution_summary']['finished_at'] for item in inputs),
        key=lambda stamp: datetime.fromisoformat(stamp.replace('Z', '+00:00')),
    )
    return value


class PrepareTests(unittest.TestCase):
    def test_rejects_long_decimal_magnitude_before_writes(self):
        for token in ('9007199254740991.0000000000000000000000000000001',
                      '-9007199254740991.0000000000000000000000000000001',
                      '9.0071992547409910000000000000000000000000000001e15',
                      '-9.0071992547409910000000000000000000000000000001e15'):
            with self.subTest(token=token):
                value = raw()
                value['benchmark_results'][0]['problem'] = {'size': 'NUMERIC_TOKEN'}
                path = self.root / 'long-token.json'
                path.write_text(json.dumps(value).replace('"NUMERIC_TOKEN"', token))
                destination = self.root / f'long-{token}'
                process = self.invoke([], extra=('--raw-run', str(path), '--data-dir', str(destination)))
                self.assertNotEqual(process.returncode, 0)
                self.assertIn('numeric', process.stderr.lower())
                self.assertFalse(destination.exists())

    def test_cli_pr_numeric_bounds_before_writes(self):
        for number in (9007199254740992, 9007199254740993):
            with self.subTest(number=number):
                destination = self.root / f'pr-{number}'
                process = self.invoke(extra=('--branch', 'feature/numeric', '--base-branch', 'develop',
                                             '--base-sha', SHA, '--pull-request-number', str(number),
                                             '--data-dir', str(destination)))
                self.assertNotEqual(process.returncode, 0)
                self.assertIn('numeric', process.stderr.lower())
                self.assertFalse(destination.exists())

    def test_cli_pr_supported_boundaries_roundtrip(self):
        for number in (1, 9007199254740991):
            with self.subTest(number=number):
                destination = self.root / f'accepted-pr-{number}'
                self.assert_ok(self.invoke(extra=('--branch', 'feature/numeric', '--base-branch', 'develop',
                                                 '--base-sha', SHA, '--pull-request-number', str(number),
                                                 '--data-dir', str(destination))))
                run_path = 'runs/side-branches/attempt-1.json'
                run = json.loads((destination / run_path).read_text())
                self.assertEqual(run['source']['pullRequest']['number'], number)
                self.assert_ok(subprocess.run([sys.executable, str(UPDATE), '--data-dir', str(destination),
                                              '--run-path', run_path], capture_output=True, text=True))
                for command in ('validate-dashboard-data.mjs', 'process-dashboard-data.mjs'):
                    result = subprocess.run(['node', str(HERE.parents[1] / command), str(destination)],
                                            capture_output=True, text=True)
                    self.assert_ok(result)
                    if command == 'process-dashboard-data.mjs':
                        exported = json.loads(result.stdout)['sourceData']['runs'][0]
                        self.assertEqual(exported['source']['pullRequest']['number'], number)

    def test_numeric_boundaries_and_fractional_roundtrip(self):
        value = raw()
        row = value['benchmark_results'][0]
        row['problem'] = {'limits': [9007199254740991, -9007199254740991, 1.25, True]}
        for samples in ([4503599627370495, 4503599627370495], [1.25], [1, 1.5], [1, 1.25, 2]):
            with self.subTest(samples=samples):
                row['timing_results_s'] = list(samples)
                destination = self.root / f'accepted-{samples}'
                self.assert_ok(self.invoke([value], extra=('--data-dir', str(destination))))
                published = json.loads((destination / 'runs/default-branch/attempt-1.json').read_text())
                actual = published['configurations'][0]['benchmark_results'][0]
                self.assertEqual(actual['timing_results_s'], samples)
                self.assertEqual(actual['status'], 'completed')
                self.assertNotIn('durationSeconds', actual)

    def test_rejects_decimal_exponent_and_underflow_tokens(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('numeric_preparer', SCRIPT)
        producer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(producer)
        for token in ('9007199254740993.0', '9.007199254740993e15', '1e-400', '9007199254740991.1'):
            path = self.root / 'numeric-token.json'
            path.write_text('{"nested":[' + token + ']}')
            with self.subTest(token=token), self.assertRaisesRegex(ValueError, 'numeric'):
                producer.read_json(path)
        path.write_text('{"nested":[9007199254740991.0,5e-324,0.0,null,true]}')
        self.assertEqual(producer.read_json(path)['nested'], [9007199254740991.0, 5e-324, 0.0, None, True])

    def test_rejects_unsupported_numeric_values_before_writes(self):
        for value, timing in ((9007199254740993, False), (10**400, False),
                              (4503599627370496, True), (9007199254740993, True), (1e308, True)):
            with self.subTest(value=value, timing=timing):
                data = raw()
                row = data['benchmark_results'][0]
                if timing:
                    row['timing_results_s'] = [value, value + 1 if value == 9007199254740993 else value]
                else:
                    row['problem'] = {'nested': [value]}
                destination = self.root / 'unsupported-numeric'
                process = self.invoke([data], extra=('--data-dir', str(destination)))
                self.assertNotEqual(process.returncode, 0)
                self.assertIn('numeric', process.stderr.lower())
                self.assertFalse(destination.exists())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / 'data'

    def invoke(self, inputs=None, run_id='attempt-1', extra=(), env=None):
        inputs = copy.deepcopy(inputs if inputs is not None else [raw()])
        # Conversion fixtures declare fictional source; pinned-source negative
        # cases use test_suite_catalog.py with an unchanged committed oracle.
        try:
            repository, self.corpus_sha = declare_fixture(self.root, inputs or [raw()])
        except (ValueError, TypeError):
            repository, self.corpus_sha = declare_fixture(self.root, [raw()])
        for value in inputs:
            actual = value['provenance']['corpus']['corpus_commit_sha']
            if isinstance(actual, str) and actual.lower() == CORPUS:
                value['provenance']['corpus']['corpus_commit_sha'] = self.corpus_sha
        extra = list(extra)
        for i, value in enumerate(extra[:-1]):
            if value == '--expected-corpus-sha' and extra[i + 1].lower() == CORPUS:
                extra[i + 1] = self.corpus_sha
        destination = self.data
        filtered = []
        index = 0
        while index < len(extra):
            if extra[index] == '--data-dir':
                destination = Path(extra[index + 1])
                index += 2
                continue
            filtered.append(extra[index])
            index += 1
        args = [
            sys.executable,
            str(SCRIPT),
            '--data-dir',
            str(destination),
            '--run-id',
            run_id,
            '--expected-sha',
            SHA,
            '--workflow-commit-sha', 'c' * 40,
            '--tensile-commit-sha', 'd' * 40,
            '--expected-corpus-sha',
            self.corpus_sha,
            '--corpus-dir', str(repository), '--manifest', 'suite.toml',
            '--machine-id',
            'worker-1',
            '--trigger',
            'auto',
            '--branch',
            'develop',
            '--commit-message',
            'Example commit',
        ]
        for i, value in enumerate(inputs):
            path = self.root / f'raw-{i}.json'
            path.write_text(json.dumps(value))
            args.extend(['--raw-run', str(path)])
        return subprocess.run(args + filtered, text=True, capture_output=True, env=env)

    def read(self, name):
        return json.loads((self.data / name).read_text())

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def snapshot(self):
        return {
            str(p.relative_to(self.data)): p.read_bytes()
            for p in self.data.rglob('*')
            if p.is_file()
        }

    def test_typed_problem_values_survive_preparation_and_consumer_export(self):
        value = raw()
        problem = {'array': [1, {'z': 'literal', 'flag': False}], 'object': {'b': 2, 'a': 1}, 'text': '[1,2]'}
        value['benchmark_results'][0]['problem'] = problem
        self.assert_ok(self.invoke([value]))
        run = self.read('runs/default-branch/attempt-1.json')
        catalog = self.read(run['benchmark_catalog'])
        self.assertEqual(catalog['benchmark_definitions']['case-1']['problem'], problem)
        self.assert_ok(subprocess.run([sys.executable, str(UPDATE), '--data-dir', str(self.data), '--run-path', 'runs/default-branch/attempt-1.json'], capture_output=True, text=True))
        processed = subprocess.run(['node', str(HERE.parents[1] / 'process-dashboard-data.mjs'), str(self.data)], capture_output=True, text=True)
        self.assert_ok(processed)
        exported = json.loads(processed.stdout)
        self.assertEqual(exported['sourceData']['catalogs'][run['benchmark_catalog']]['benchmark_definitions']['case-1']['problem'], problem)
        self.assertEqual(exported['data']['runs'][0]['tests'][0]['problem'], problem)

    def test_cli_omits_unused_website_metadata_arguments(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), '--help'], text=True, capture_output=True
        )
        self.assert_ok(result)
        self.assertNotIn('--repository', result.stdout)
        self.assertNotIn('--is-beta', result.stdout)

    def test_cli_requires_raw_runs_not_a_prepared_dataset(self):
        prepared = self.root / 'prepared'
        self.assert_ok(self.invoke(extra=('--data-dir', str(prepared))))
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                '--prepared-data',
                str(prepared),
                '--data-dir',
                str(self.data),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn('--raw-run', result.stderr)
        self.assertFalse(self.data.exists())

    def test_builder_leaves_existing_index_and_metadata_untouched(self):
        staging = self.root / 'staging'
        staging.mkdir()
        metadata = staging / 'metadata.json'
        index = staging / 'index.json'
        metadata.write_bytes(b'{"keep": true}\n')
        index.write_bytes(b'{"runFiles": []}\n')
        value = raw()
        repository, corpus_sha = declare_fixture(self.root, [value])
        value['provenance']['corpus']['corpus_commit_sha'] = corpus_sha
        raw_path = self.root / 'one-raw.json'
        raw_path.write_text(json.dumps(value))
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                '--raw-run',
                str(raw_path),
                '--data-dir',
                str(staging),
                '--run-id',
                'attempt-1',
                '--expected-sha',
                SHA,
                '--workflow-commit-sha', 'c' * 40,
                '--tensile-commit-sha', 'd' * 40,
                '--expected-corpus-sha',
                corpus_sha,
                '--corpus-dir', str(repository), '--manifest', 'suite.toml',
                '--machine-id',
                'worker-1',
                '--trigger',
                'auto',
                '--branch',
                'develop',
                '--commit-message',
                'Example commit',
            ],
            text=True,
            capture_output=True,
        )
        self.assert_ok(result)
        self.assertEqual(metadata.read_bytes(), b'{"keep": true}\n')
        self.assertEqual(index.read_bytes(), b'{"runFiles": []}\n')
        self.assertTrue(
            (staging / 'runs' / 'default-branch' / 'attempt-1.json').is_file()
        )

    def test_preparer_requires_git_but_not_node(self):
        environment = dict(os.environ)
        tools = self.root / 'git-only'
        tools.mkdir()
        (tools / 'git').symlink_to(shutil.which('git'))
        environment['PATH'] = str(tools)
        self.assert_ok(self.invoke(env=environment))
        self.assertTrue((self.data / 'runs/default-branch/attempt-1.json').is_file())
        self.assertFalse((self.data / 'index.json').exists())

    def test_new_schema_one_preserves_raw_metadata_and_explicit_tool_revisions(self):
        value = raw()
        value['provenance']['auxiliary']['nested'] = {'value': [None, True, 'null']}
        self.assert_ok(self.invoke([value], extra=(
            '--workflow-commit-sha', 'c' * 40,
            '--tensile-commit-sha', 'd' * 40,
        )))
        run = self.read('runs/default-branch/attempt-1.json')
        self.assertEqual(set(run), {'schemaVersion', 'id', 'benchmark_catalog',
                                    'source', 'execution', 'execution_summary',
                                    'provenance', 'configurations'})
        self.assertEqual(run['execution_summary'], value['execution_summary'])
        self.assertEqual(run['source'], {'branch': 'develop', 'message': 'Example commit'})
        self.assertEqual(run['execution'], {'trigger': 'auto', 'machine_label': 'worker-1'})
        self.assertEqual(run['provenance']['rocjitsu']['rocjitsu_commit_sha'], SHA)
        self.assertEqual(run['provenance']['rocjitsu']['workflow_commit_sha'], 'c' * 40)
        self.assertEqual(run['provenance']['auxiliary']['tensile_commit_sha'], 'd' * 40)
        self.assertEqual(run['provenance']['auxiliary']['nested'], {'value': [None, True, 'null']})
        catalog = self.read(run['benchmark_catalog'])
        self.assertEqual(catalog, {
            'benchmark_suite': 'smoke',
            'benchmark_definitions': {'case-1': {
                'suite': 'smoke', 'name': 'Example', 'operation': 'Example computation',
                'problem': {'size': 8},
            }},
            'membership': {'gfx950': {'single': ['case-1']}},
        })
        self.assertEqual(run['configurations'], [{
            'target': 'gfx950', 'thread_policy': 'single', 'benchmark_results': [{
                'id': 'case-1', 'status': 'completed', 'timing_results_s': [1, 9, 2], 'error': None,
            }],
        }])

    def test_tool_revision_conflicts_reject_before_writes(self):
        for section, key, actual in (
            ('rocjitsu', 'workflow_commit_sha', 'e' * 40),
            ('auxiliary', 'tensile_commit_sha', None),
        ):
            with self.subTest(key=key):
                value = raw()
                value['provenance'][section][key] = actual
                rejected = self.invoke([value], extra=(
                    '--workflow-commit-sha', 'c' * 40,
                    '--tensile-commit-sha', 'd' * 40,
                ))
                self.assertNotEqual(rejected.returncode, 0)
                self.assertIn('Conflicting raw ' + key, rejected.stderr)
                self.assertFalse(self.data.exists())

    def test_cli_requires_valid_explicit_tool_revisions(self):
        for flag in ('--workflow-commit-sha', '--tensile-commit-sha'):
            for invalid in ('', 'abc', 'g' * 40, 'a' * 40 + ' '):
                with self.subTest(flag=flag, invalid=invalid):
                    rejected = self.invoke(extra=(flag, invalid))
                    self.assertNotEqual(rejected.returncode, 0)
                    self.assertIn('40-hex SHA', rejected.stderr)
                    self.assertFalse(self.data.exists())

    def test_open_provenance_extension_must_agree_across_inputs(self):
        first, second = raw(), raw('default')
        first['provenance']['extension'] = {'nested': {'a': True}}
        second['provenance']['extension'] = {'nested': {'a': 1}}
        result = self.invoke([first, second])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Inconsistent extension provenance', result.stderr)
        self.assertFalse(self.data.exists())

    def test_produces_schema_one_median_results(self):
        self.assert_ok(self.invoke())
        self.assertFalse((self.data / 'metadata.json').exists())
        run = self.read('runs/default-branch/attempt-1.json')
        self.assertIs(type(run['schemaVersion']), int)
        self.assertEqual(run['schemaVersion'], 1)
        self.assertFalse((self.data / 'index.json').exists())
        self.assertNotIn('schemaVersion', self.read(run['benchmark_catalog']))
        self.assertEqual(run['provenance']['rocjitsu']['rocjitsu_commit_sha'], SHA)
        self.assertEqual(run['execution_summary']['finished_at'], '2026-01-01T01:01:00Z')
        config = run['configurations'][0]
        self.assertEqual(config['thread_policy'], 'single')
        self.assertNotIn('threadingMode', config)
        self.assertNotIn('thread_policy', config['benchmark_results'][0])
        self.assertEqual(
            self.read(run['benchmark_catalog'])['membership'],
            {'gfx950': {'single': ['case-1']}},
        )
        self.assertEqual(config['benchmark_results'][0]['timing_results_s'], [1, 9, 2])
        self.assertEqual(config['benchmark_results'][0]['error'], None)
        self.assertEqual(config['benchmark_results'][0]['id'], 'case-1')
        self.assertEqual(
            self.read(run['benchmark_catalog'])['benchmark_definitions']['case-1']['operation'],
            'Example computation',
        )
        self.assertEqual(
            sorted(
                path.relative_to(self.data).as_posix()
                for path in self.data.rglob('*.json')
            ),
            sorted(
                [
                    'runs/default-branch/attempt-1.json',
                    run['benchmark_catalog'],
                ]
            ),
        )

    def test_consolidated_run_preserves_identity_operation_and_sparse_policies(self):
        value = raw('default')
        value['execution_summary']['benchmark_suite'] = 'performance-v1'
        value['benchmark_results'] = []
        for target, policy, status, samples in (
            ('gfx950', 'default', 'completed', [9, 1, 2]),
            ('gfx950', 'single', 'failed', [5, 2]),
            ('gfx1250', 'default', 'timeout', []),
            ('gfx1250', 'single', 'failed', []),
        ):
            result = copy.deepcopy(raw()['benchmark_results'][0])
            result.update(
                id='gemm-and-reduce.default',
                target=target,
                thread_policy=policy,
                operation='Matrix multiplication followed by reduction',
                status=status,
                timing_results_s=samples,
                exit_code=0 if status == 'completed' else None,
                error=None if status == 'completed' else 'Incomplete execution',
            )
            value['benchmark_results'].append(result)
        self.assert_ok(self.invoke([value]))
        run = self.read('runs/default-branch/attempt-1.json')
        catalog = self.read(run['benchmark_catalog'])
        self.assertEqual(list(catalog['benchmark_definitions']), ['gemm-and-reduce.default'])
        self.assertEqual(
            catalog['benchmark_definitions']['gemm-and-reduce.default']['operation'],
            'Matrix multiplication followed by reduction',
        )
        configs = {(c['target'], c['thread_policy']): c for c in run['configurations']}
        self.assertEqual(
            set(configs),
            {('gfx950', 'default'), ('gfx950', 'single'), ('gfx1250', 'default'), ('gfx1250', 'single')},
        )
        for result in value['benchmark_results']:
            prepared = configs[result['target'], result['thread_policy']]['benchmark_results'][0]
            self.assertNotIn('thread_policy', prepared)
            self.assertEqual(prepared['id'], result['id'])
            self.assertEqual(prepared['timing_results_s'], result['timing_results_s'])
            self.assertEqual(prepared['status'], result['status'])
            self.assertNotIn('durationSeconds', prepared)
        self.assertEqual(run['execution_summary']['benchmark_suite'], 'performance-v1')
        self.assertEqual(run['execution_summary']['samples'], 3)
        original = self.snapshot()
        value['benchmark_results'].reverse()
        self.assert_ok(self.invoke([value]))
        self.assertEqual(self.snapshot(), original)

    def test_same_definition_with_different_ids_is_not_collapsed(self):
        value = raw()
        other = copy.deepcopy(value['benchmark_results'][0])
        other['id'] = 'case-2'
        value['benchmark_results'].append(other)
        self.assert_ok(self.invoke([value]))
        run = self.read('runs/default-branch/attempt-1.json')
        self.assertEqual(
            list(self.read(run['benchmark_catalog'])['benchmark_definitions']),
            ['case-1', 'case-2'],
        )

    def test_unsupported_policy_and_unsafe_target_reject_before_writes(self):
        for key, invalid in (('thread_policy', 'ST'), ('thread_policy', 'MT'), ('thread_policy', 'Adaptive / workers'), ('target', 'Target / variant')):
            with self.subTest(key=key, value=invalid):
                value = raw()
                value['benchmark_results'][0][key] = invalid
                result = self.invoke([value])
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.data.exists())

    def test_literal_target_and_policy_strings_are_preserved(self):
        value = raw()
        value['benchmark_results'] = []
        pairs = [
            ('gfx950', 'default'),
            ('gfx950', 'single'),
            ('gfx950-variant', 'single'),
        ]
        for target, policy in pairs:
            result = copy.deepcopy(raw()['benchmark_results'][0])
            result.update(target=target, thread_policy=policy)
            if target == 'gfx950-variant': result['id'] = 'variant-case'
            value['benchmark_results'].append(result)
        self.assert_ok(self.invoke([value]))
        run = self.read('runs/default-branch/attempt-1.json')
        self.assertEqual(
            [
                (config['target'], config['thread_policy'])
                for config in run['configurations']
            ],
            sorted(pairs),
        )
        self.assertEqual(
            self.read(run['benchmark_catalog'])['membership'],
            {'gfx950': {'default': ['case-1'], 'single': ['case-1']},
             'gfx950-variant': {'single': ['variant-case']}},
        )
        for config in run['configurations']:
            self.assertNotIn('thread_policy', config['benchmark_results'][0])
        before = self.snapshot()
        value['benchmark_results'].reverse()
        self.assert_ok(self.invoke([value]))
        self.assertEqual(self.snapshot(), before)

    def test_mixed_policies_survive_consumer_normalization_for_same_workload(self):
        policies = ['single', 'default']
        value = raw()
        value['benchmark_results'] = [
            raw(policy)['benchmark_results'][0] for policy in policies
        ]
        self.assert_ok(self.invoke([value]))
        run = self.read('runs/default-branch/attempt-1.json')
        self.assertEqual(
            {config['thread_policy'] for config in run['configurations']}, set(policies)
        )
        for config in run['configurations']:
            self.assertEqual(config['target'], 'gfx950')
            self.assertEqual(config['benchmark_results'][0]['id'], 'case-1')
            self.assertNotIn('thread_policy', config['benchmark_results'][0])
        self.assert_ok(
            subprocess.run(
                [
                    sys.executable,
                    str(UPDATE),
                    '--data-dir',
                    str(self.data),
                    '--run-path',
                    'runs/default-branch/attempt-1.json',
                ],
                capture_output=True,
                text=True,
            )
        )
        processed = subprocess.run(
            [
                'node',
                str(HERE.parents[1] / 'process-dashboard-data.mjs'),
                str(self.data),
            ],
            capture_output=True,
            text=True,
        )
        self.assert_ok(processed)
        normalized = json.loads(processed.stdout)['data']['runs'][0]['tests']
        self.assertEqual(
            {
                (test['logicalTestId'], test['target'], test['thread_policy'])
                for test in normalized
            },
            {('case-1', 'gfx950', policy) for policy in policies},
        )

    def test_conflicting_workload_definitions_reject_before_writes(self):
        for key, changed in (
            ('suite', 'different'),
            ('name', 'Different name'),
            ('operation', 'Different computation'),
            ('problem', {'size': 16}),
            ('problem', {'size': True}),
        ):
            for separate_files in (False, True):
                with self.subTest(
                    key=key, changed=changed, separate_files=separate_files
                ):
                    first, second = raw(), raw('default')
                    second['benchmark_results'][0][key] = changed
                    inputs = [first, second]
                    if not separate_files:
                        first['benchmark_results'].extend(second['benchmark_results'])
                        inputs = [first]
                    result = self.invoke(inputs)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertRegex(result.stderr, 'definition mismatch|Incomplete manifest matrix')
                    self.assertFalse(self.data.exists())

    def test_duplicate_result_identity_rejected_within_and_across_files(self):
        result = self.invoke([raw(), raw()])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Duplicate result identity', result.stderr)
        self.assertFalse(self.data.exists())
        value = raw()
        value['benchmark_results'].append(copy.deepcopy(value['benchmark_results'][0]))
        result = self.invoke([value])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Duplicate result identity', result.stderr)
        self.assertFalse(self.data.exists())

    def test_unknown_sdk_version_is_preserved_as_null_environment_fact(self):
        value = raw()
        value['provenance']['rocjitsu']['rocm_sdk_version'] = None
        self.assert_ok(self.invoke([value]))
        run = self.read('runs/default-branch/attempt-1.json')
        self.assertIsNone(run['provenance']['rocjitsu']['rocm_sdk_version'])

    def test_same_policy_disjoint_targets_can_be_prepared_without_hash_checks(self):
        first, second = raw(), raw()
        second['benchmark_results'][0]['target'] = 'gfx1250'
        # Target hashes are retained as typed provenance, not validated as identities.
        first['provenance']['rocjitsu']['target_config_sha256'] = {'gfx950': 'unused'}
        second['provenance']['rocjitsu']['target_config_sha256'] = None
        self.assert_ok(self.invoke([consolidated(first, second)]))
        run = self.read('runs/default-branch/attempt-1.json')
        self.assertEqual(len(run['configurations']), 2)
        self.assertEqual(run['provenance']['rocjitsu']['target_config_sha256'], {'gfx950': 'unused'})

    def test_missing_row_policy_or_operation_is_not_inferred_from_summary(self):
        for field in ('thread_policy', 'operation'):
            with self.subTest(field=field):
                value = raw()
                value['execution_summary']['threading_mode'] = 'single'
                del value['benchmark_results'][0][field]
                result = self.invoke([value])
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(field, result.stderr)
                self.assertFalse(self.data.exists())

    def test_definition_conflict_keeps_seeded_publication_unchanged(self):
        self.assert_ok(self.invoke())
        before = self.snapshot()
        first, second = raw(), raw('default')
        first['benchmark_results'][0]['problem'] = {'flag': False}
        second['benchmark_results'][0]['problem'] = {'flag': 0}
        first['benchmark_results'].extend(second['benchmark_results'])
        result = self.invoke([first], run_id='attempt-2')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('definition mismatch', result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_timing_samples_survive_publication_and_consumer_normalization(self):
        value = raw()
        cases = [
            ('completed', [1, 9, 2], 2),
            ('completed', [9, 1, 4, 2], 3),
            ('failed', [5, 2], None),
            ('timeout', [], None),
        ]
        value['benchmark_results'] = []
        for index, (status, samples, _) in enumerate(cases):
            result = copy.deepcopy(raw()['benchmark_results'][0])
            result.update(
                id=f'case-{index}',
                name=f'Example {index}',
                status=status,
                timing_results_s=samples,
                exit_code=0 if status == 'completed' else 1,
                error=None if status == 'completed' else 'Incomplete execution',
            )
            value['benchmark_results'].append(result)
        self.assert_ok(self.invoke([value]))
        run = self.read('runs/default-branch/attempt-1.json')
        catalog = self.read(run['benchmark_catalog'])
        names = {identity: test['name'] for identity, test in catalog['benchmark_definitions'].items()}
        published = {
            names[result['id']]: result
            for result in run['configurations'][0]['benchmark_results']
        }
        (self.data / 'index.json').write_text(
            json.dumps(
                {
                    'generatedAt': '2026-01-01T02:00:00Z',
                    'runFiles': ['runs/default-branch/attempt-1.json'],
                }
            )
        )
        processed = subprocess.run(
            [
                'node',
                str(HERE.parents[1] / 'process-dashboard-data.mjs'),
                str(self.data),
            ],
            text=True,
            capture_output=True,
        )
        self.assert_ok(processed)
        normalized = {
            test['name']: test
            for test in json.loads(processed.stdout)['data']['runs'][0]['tests']
        }
        for index, (status, samples, duration) in enumerate(cases):
            for results in (published, normalized):
                result = results[f'Example {index}']
                self.assertEqual(result.get('timing_results_s'), samples)
                self.assertEqual(result['status'], status)
            self.assertNotIn('durationSeconds', published[f'Example {index}'])
            self.assertEqual(normalized[f'Example {index}']['durationSeconds'], duration)
            self.assertEqual(
                normalized[f'Example {index}']['logicalTestId'], f'case-{index}'
            )
            self.assertEqual(
                normalized[f'Example {index}']['operation'], 'Example computation'
            )

    def test_uppercase_git_shas_are_published_in_lowercase(self):
        value = raw()
        value['provenance']['rocjitsu']['rocjitsu_commit_sha'] = SHA.upper()
        value['provenance']['corpus']['corpus_commit_sha'] = CORPUS.upper()
        self.assert_ok(
            self.invoke(
                [value],
                extra=(
                    '--expected-sha',
                    SHA.upper(),
                    '--expected-corpus-sha',
                    CORPUS.upper(),
                ),
            )
        )
        run = self.read('runs/default-branch/attempt-1.json')
        self.assertEqual(run['provenance']['rocjitsu']['rocjitsu_commit_sha'], SHA)
        self.assertEqual(run['provenance']['corpus']['corpus_commit_sha'], self.corpus_sha)
        before = self.snapshot()
        self.assert_ok(self.invoke())
        self.assertEqual(self.snapshot(), before)

    def test_git_sha_provenance_matching_ignores_only_hex_case(self):
        single, multi = raw(), raw('default')
        single['provenance']['rocjitsu']['rocjitsu_commit_sha'] = 'Aa' * 20
        single['provenance']['corpus']['corpus_commit_sha'] = CORPUS.upper()
        self.assert_ok(
            self.invoke(
                [consolidated(single, multi)],
                extra=(
                    '--expected-sha',
                    SHA.upper(),
                    '--expected-corpus-sha',
                    'bB' * 20,
                ),
            )
        )
        run = self.read('runs/default-branch/attempt-1.json')
        self.assertEqual(run['provenance']['rocjitsu']['rocjitsu_commit_sha'], SHA)
        self.assertEqual(len(run['configurations']), 2)
        self.assertEqual(run['provenance']['corpus']['corpus_commit_sha'], self.corpus_sha)
        before = self.snapshot()
        for flag, expected in (
            ('--expected-sha', 'D' * 40),
            ('--expected-corpus-sha', 'D' * 40),
            ('--expected-sha', 'A' * 39),
            ('--expected-corpus-sha', 'B' * 40 + ' '),
        ):
            with self.subTest(flag=flag, expected=expected):
                result = self.invoke([single, multi], extra=(flag, expected))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('SHA', result.stderr)
                self.assertNotIn('Traceback', result.stderr)
                self.assertEqual(self.snapshot(), before)

    def test_completed_result_accepts_null_exit_code(self):
        value = raw()
        value['benchmark_results'][0]['exit_code'] = None
        self.assert_ok(self.invoke([value]))
        result = self.read('runs/default-branch/attempt-1.json')['configurations'][0][
            'benchmark_results'
        ][0]
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['timing_results_s'], [1, 9, 2])
        self.assertNotIn('durationSeconds', result)
        self.assertIsNone(result['error'])

    def test_explicit_policies_share_definitions_with_asymmetric_membership(self):
        single, multi = raw(), raw('default')
        single['execution_summary']['benchmark_suite'] = 'performance-v1'
        multi['execution_summary']['benchmark_suite'] = 'performance-v1'
        single['benchmark_results'][0]['id'] = 'example'
        multi['benchmark_results'][0]['id'] = 'example'
        problem = {
            'nested': {'z': 'literal', 'a': [1, False]},
            'bool': False,
            'zero': 0,
            'text': 'value',
        }
        for value in (single, multi):
            value['benchmark_results'][0]['problem'] = copy.deepcopy(problem)
            value['provenance']['auxiliary'] = {'nested': {'b': 1, 'a': None}}

        failed = copy.deepcopy(single['benchmark_results'][0])
        failed.update(
            id='failure',
            name='Failed workload',
            status='failed',
            error='Exit failure',
            exit_code=1,
            timing_results_s=[5],
        )
        timeout = copy.deepcopy(failed)
        timeout.update(
            id='timeout', name='Timeout workload', status='timeout', error=None
        )
        single['benchmark_results'].extend([failed, timeout])
        self.assert_ok(self.invoke([consolidated(single, multi)]))
        run = self.read('runs/default-branch/attempt-1.json')
        configs = {c['thread_policy']: c for c in run['configurations']}
        single_success = next(
            r for r in configs['single']['benchmark_results'] if r['status'] == 'completed'
        )
        self.assertEqual(
            single_success['id'], configs['default']['benchmark_results'][0]['id']
        )
        for result in configs['single']['benchmark_results']:
            if result['status'] != 'completed':
                self.assertNotIn('durationSeconds', result)
        catalog = self.read(run['benchmark_catalog'])
        definition = catalog['benchmark_definitions'][single_success['id']]
        self.assertEqual(
            definition['problem'],
            {
                'nested': {'a': [1, False], 'z': 'literal'},
                'bool': False,
                'zero': 0,
                'text': 'value',
            },
        )
        self.assertEqual(run['provenance']['machine']['hostname'], 'worker')
        self.assertEqual(run['provenance']['auxiliary']['nested'], {'a': None, 'b': 1})
        self.assertEqual(run['execution_summary']['timestamp'], single['execution_summary']['timestamp'])

    def test_candidate_retry_and_definition_changes_are_immutable(self):
        self.assert_ok(self.invoke())
        original = self.snapshot()
        self.assert_ok(self.invoke())
        self.assertEqual(
            self.snapshot(), original, 'Exact retry must be byte-preserving'
        )
        revised = raw()
        revised['execution_summary'].update(
            timestamp='2026-01-02T01:00:00Z',
            finished_at='2026-01-02T01:01:00Z',
            wall_time_s=50,
        )
        self.assert_ok(self.invoke([revised], run_id='attempt-2'))
        old = self.read('runs/default-branch/attempt-1.json')
        new = self.read('runs/default-branch/attempt-2.json')
        self.assertEqual(old['benchmark_catalog'], new['benchmark_catalog'])
        self.assertEqual(old['provenance'], new['provenance'])
        revised['benchmark_results'][0]['problem']['size'] = 16
        rejected = self.invoke([revised], run_id='attempt-3')
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('Immutable resource conflict', rejected.stderr)
        revised['execution_summary']['benchmark_suite'] = 'smoke-v2'
        revised['benchmark_results'][0]['id'] = 'case-v2'
        self.assert_ok(self.invoke([revised], run_id='attempt-3'))
        changed = self.read('runs/default-branch/attempt-3.json')
        self.assertNotEqual(old['benchmark_catalog'], changed['benchmark_catalog'])
        self.assertNotEqual(
            old['configurations'][0]['benchmark_results'][0]['id'],
            changed['configurations'][0]['benchmark_results'][0]['id'],
        )
        self.assertEqual(
            (self.data / 'runs/default-branch/attempt-1.json').read_bytes(),
            original['runs/default-branch/attempt-1.json'],
        )
        before_conflict = self.snapshot()
        conflict = self.invoke([revised])
        self.assertNotEqual(conflict.returncode, 0)
        self.assertIn('immutable', conflict.stderr.lower())
        self.assertEqual(self.snapshot(), before_conflict)

    def test_invalid_raw_facts_reject_before_any_writes(self):
        cases = [
            (('execution_summary', 'finished_at'), None),
            (('execution_summary', 'finished_at'), '2026-02-30T01:00:00Z'),
            (('execution_summary', 'timestamp'), '2026-01-01'),
            (('execution_summary', 'timestamp'), '2026-01-02T01:00:00Z'),
            (('execution_summary', 'warmups'), -1),
            (('execution_summary', 'warmups'), True),
            (('execution_summary', 'samples'), 0),
            (('execution_summary', 'samples'), 1.5),
            (('execution_summary', 'timeout_seconds'), 0),
            (('execution_summary', 'wall_time_s'), float('inf')),
            (('benchmark_results', 0, 'thread_policy'), ''),
            (('benchmark_results', 0, 'thread_policy'), None),
            (('benchmark_results', 0, 'thread_policy'), []),
            (('benchmark_results', 0, 'operation'), ''),
            (('provenance', 'rocjitsu', 'rocjitsu_commit_sha'), None),
            (('provenance', 'rocjitsu', 'rocjitsu_commit_sha'), 'd' * 40),
            (('provenance', 'rocjitsu', 'rocjitsu_commit_timestamp'), None),
            (('provenance', 'rocjitsu', 'rocm_sdk_version'), ''),
            (('provenance', 'corpus', 'corpus_commit_sha'), 'd' * 40),
            (('provenance', 'corpus', 'corpus_commit_timestamp'), None),
            (('provenance', 'machine', 'hostname'), ''),
            (('provenance', 'auxiliary'), []),
            (('benchmark_results', 0, 'timing_results_s'), []),
            (('benchmark_results', 0, 'timing_results_s'), [0]),
            (('benchmark_results', 0, 'timing_results_s'), [True]),
            (('benchmark_results', 0, 'timing_results_s'), [float('nan')]),
            (('benchmark_results', 0, 'exit_code'), '0'),
            (('benchmark_results', 0, 'exit_code'), 1),
            (('benchmark_results', 0, 'error'), 'completed with error'),
            (('benchmark_results', 0, 'problem'), []),
            (('benchmark_results', 0, 'name'), ''),
            (('benchmark_results', 0, 'target'), ''),
        ]
        for keys, value in cases:
            with self.subTest(keys=keys, value=value):
                record = raw()
                obj = record
                for key in keys[:-1]:
                    obj = obj[key]
                obj[keys[-1]] = value
                result = self.invoke([record])
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn('error:', result.stderr)
                self.assertNotIn('Traceback', result.stderr)
                self.assertFalse(self.data.exists())

    def test_cross_input_provenance_and_protocol_must_agree(self):
        changes = [
            (('provenance', 'machine', 'cpu'), 'Different CPU'),
            (('provenance', 'rocjitsu', 'rocm_sdk_version'), '8.0'),
            (
                ('provenance', 'rocjitsu', 'rocjitsu_commit_timestamp'),
                '2025-12-31T00:00:00Z',
            ),
            (
                ('provenance', 'corpus', 'corpus_commit_timestamp'),
                '2025-11-30T00:00:00Z',
            ),
            (('provenance', 'auxiliary'), {'different': True}),
            (('execution_summary', 'samples'), 4),
            (('execution_summary', 'warmups'), 2),
            (('execution_summary', 'timeout_seconds'), 120),
            (('execution_summary', 'benchmark_suite'), 'different-suite'),
        ]
        for keys, value in changes:
            with self.subTest(keys=keys):
                multi = raw('default')
                obj = multi
                for key in keys[:-1]:
                    obj = obj[key]
                obj[keys[-1]] = value
                result = self.invoke([raw(), multi])
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('inconsistent', result.stderr.lower())
                self.assertFalse(self.data.exists())

    def test_reordered_inputs_are_idempotent_and_completion_uses_instants(self):
        single, multi = raw(), raw('default')
        single['execution_summary']['finished_at'] = '2026-01-01T04:00:00+02:00'
        multi['execution_summary']['finished_at'] = '2026-01-01T03:00:00Z'
        for value in (single, multi):
            extra = copy.deepcopy(value['benchmark_results'][0])
            extra.update(id='second', name='Another definition')
            value['benchmark_results'].append(extra)
        self.assert_ok(self.invoke([consolidated(single, multi)]))
        self.assertEqual(
            self.read('runs/default-branch/attempt-1.json')['execution_summary']['finished_at'],
            '2026-01-01T03:00:00Z',
        )
        original = self.snapshot()
        single['benchmark_results'].reverse()
        multi['benchmark_results'].reverse()
        self.assert_ok(self.invoke([consolidated(multi, single)]))
        self.assertEqual(self.snapshot(), original)

    def test_path_traversal_rejected_without_staging_escape(self):
        for run_id in ('../../escaped', '/absolute', 'a/b', '%2e%2e', '.', '..', 'a?b'):
            with self.subTest(run_id=run_id):
                result = self.invoke(
                    run_id=run_id, env={**os.environ, 'TMPDIR': str(self.root)}
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('run-id', result.stderr)
                self.assertFalse((self.root / 'escaped.json').exists())
                self.assertFalse(self.data.exists())

    def test_symlink_output_rejected_without_touching_external_files(self):
        outside = self.root / 'outside'
        outside.mkdir()
        marker = outside / 'marker'
        marker.write_text('keep')
        self.data.mkdir()
        (self.data / 'runs').symlink_to(outside, target_is_directory=True)
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('symlink', result.stderr.lower())
        self.assertEqual(list(outside.iterdir()), [marker])
        self.assertFalse((self.data / 'metadata.json').exists())
        (self.data / 'runs').unlink()
        self.data.rmdir()
        self.data.symlink_to(outside, target_is_directory=True)
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('symlink', result.stderr.lower())
        self.assertEqual(list(outside.iterdir()), [marker])

    def test_cli_errors_are_actionable(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT)], text=True, capture_output=True
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn('--raw-run', result.stderr)
        for extra in (
            ('--trigger', 'invalid'),
            ('--expected-sha', 'short'),
            ('--branch', ''),
        ):
            with self.subTest(extra=extra):
                result = self.invoke(extra=extra)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('Traceback', result.stderr)
                self.assertFalse(self.data.exists())

    def test_duplicate_json_keys_are_rejected(self):
        path = self.root / 'duplicate.json'
        value = json.dumps(raw()).replace('"warmups": 1', '"warmups": -1, "warmups": 1')
        path.write_text(value)
        result = self.invoke(inputs=[], extra=('--raw-run', str(path)))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Duplicate JSON key', result.stderr)
        self.assertFalse(self.data.exists())

    def test_metadata_and_unrelated_runs_are_not_read_or_updated(self):
        self.data.mkdir()
        metadata = self.data / 'metadata.json'
        metadata.write_bytes(b'not even JSON: stale website settings\n')
        self.assert_ok(self.invoke())
        self.assertEqual(
            metadata.read_bytes(), b'not even JSON: stale website settings\n'
        )
        before = self.snapshot()
        self.assert_ok(self.invoke())
        self.assertEqual(self.snapshot(), before)
        old_run = self.read('runs/default-branch/attempt-1.json')
        old_run['configurations'][0]['benchmark_results'] = []
        (self.data / 'runs/default-branch/attempt-1.json').write_text(
            json.dumps(old_run)
        )
        before = self.snapshot()
        # Full wire-schema validation is separate. Preparing a new candidate does
        # not inspect or rewrite unrelated run history.
        self.assert_ok(self.invoke(run_id='attempt-2'))
        self.assertEqual(
            (self.data / 'runs/default-branch/attempt-1.json').read_bytes(),
            before['runs/default-branch/attempt-1.json'],
        )
        self.assertTrue((self.data / 'runs/default-branch/attempt-2.json').is_file())
        self.assertFalse((self.data / 'index.json').exists())

    def test_candidate_resources_are_reused_but_conflicts_rejected(self):
        self.assert_ok(self.invoke())
        existing_run = (self.data / 'runs/default-branch/attempt-1.json').read_bytes()
        self.assert_ok(self.invoke())
        self.assertEqual(
            (self.data / 'runs/default-branch/attempt-1.json').read_bytes(),
            existing_run,
        )
        run = self.read('runs/default-branch/attempt-1.json')
        catalog = self.read(run['benchmark_catalog'])
        catalog['benchmark_definitions']['case-1']['name'] = 'Corrupted orphan'
        (self.data / run['benchmark_catalog']).write_text(json.dumps(catalog))
        before = self.snapshot()
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Immutable resource conflict', result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_duplicate_logical_results_and_future_completion_are_rejected(self):
        value = raw()
        value['benchmark_results'].append(copy.deepcopy(value['benchmark_results'][0]))
        result = self.invoke([value])
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.data.exists())
        value = raw()
        value['execution_summary']['finished_at'] = '9999-01-01T00:00:00Z'
        result = self.invoke([value])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('completed by publication', result.stderr)
        self.assertFalse(self.data.exists())

    def test_side_branch_source_base_and_pull_request_are_published(self):
        input_base_sha = 'Dd' * 20
        expected_base_sha = input_base_sha.lower()
        self.assert_ok(
            self.invoke(
                extra=(
                    '--branch',
                    'feature/example',
                    '--trigger',
                    'manual',
                    '--base-branch',
                    'develop',
                    '--base-sha',
                    input_base_sha,
                    '--pull-request-number',
                    '13059',
                    '--pull-request-url',
                    'https://github.com/ROCm/rocm-systems/pull/13059',
                )
            )
        )
        run = self.read('runs/side-branches/attempt-1.json')
        self.assertEqual(
            run['source']['base'],
            {'branch': 'develop', 'commit': expected_base_sha},
        )
        self.assertEqual(
            run['source']['pullRequest'],
            {
                'number': 13059,
                'url': 'https://github.com/ROCm/rocm-systems/pull/13059',
            },
        )

    def test_pull_request_url_host_matches_consumer_contract(self):
        arguments = (
            '--branch',
            'feature/example',
            '--trigger',
            'manual',
            '--base-branch',
            'develop',
            '--base-sha',
            'd' * 40,
            '--pull-request-number',
            '1',
            '--pull-request-url',
        )
        for host in (
            'example.com',
            'github.com.example.com',
            'github.com:bad',
            'github.com:99999',
        ):
            with self.subTest(host=host):
                destination = self.root / host
                result = self.invoke(
                    extra=arguments
                    + (
                        f'https://{host}/ROCm/rocm-systems/pull/1',
                        '--data-dir',
                        str(destination),
                    )
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Pull request URL', result.stderr)
                self.assertFalse(destination.exists())
        self.assert_ok(
            self.invoke(
                extra=arguments + ('https://github.com/ROCm/rocm-systems/pull/1',)
            )
        )
        self.assertEqual(
            self.read('runs/side-branches/attempt-1.json')['source']['pullRequest'][
                'url'
            ],
            'https://github.com/ROCm/rocm-systems/pull/1',
        )

    def test_side_branch_source_base_without_pull_request_is_published(self):
        self.assert_ok(
            self.invoke(
                extra=(
                    '--branch',
                    'feature/example',
                    '--trigger',
                    'manual',
                    '--base-branch',
                    'develop',
                    '--base-sha',
                    'd' * 40,
                )
            )
        )
        source = self.read('runs/side-branches/attempt-1.json')['source']
        self.assertEqual(source['base'], {'branch': 'develop', 'commit': 'd' * 40})
        self.assertNotIn('pullRequest', source)

    def test_source_base_and_pull_request_arguments_are_consistent(self):
        cases = (
            (('--base-branch', 'develop'), 'base'),
            (('--base-sha', 'd' * 40), 'base'),
            (
                (
                    '--branch',
                    'feature/example',
                    '--base-branch',
                    'develop',
                    '--base-sha',
                    'short',
                ),
                'SHA',
            ),
            (('--pull-request-number', '0'), 'pull request'),
            (
                ('--pull-request-url', 'https://github.com/ROCm/rocm-systems/pull/1'),
                'pull request',
            ),
            (
                (
                    '--pull-request-number',
                    '1',
                    '--pull-request-url',
                    'https://github.com/ROCm/rocm-systems/pull/2',
                ),
                'pull request',
            ),
        )
        for extra, message in cases:
            with self.subTest(extra=extra):
                result = self.invoke(extra=extra)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message.lower(), result.stderr.lower())
                self.assertFalse(self.data.exists())

    def test_suite_named_catalog_and_target_independent_workloads(self):
        value = raw()
        other = copy.deepcopy(value['benchmark_results'][0])
        other.update(target='gfx1250')
        value['benchmark_results'].append(other)

        self.assert_ok(
            self.invoke(
                [value], extra=('--branch', 'feature/example', '--trigger', 'manual')
            )
        )
        self.assertFalse((self.data / 'index.json').exists())
        run = self.read('runs/side-branches/attempt-1.json')
        self.assertEqual(run['execution']['trigger'], 'manual')
        self.assertEqual(run['source']['branch'], 'feature/example')
        self.assertEqual(
            run['configurations'][0]['benchmark_results'][0]['id'],
            run['configurations'][1]['benchmark_results'][0]['id'],
        )
        catalog = self.read(run['benchmark_catalog'])
        self.assertEqual(catalog['benchmark_suite'], 'smoke')
        self.assertEqual(run['execution']['machine_label'], 'worker-1')

    def test_retry_preserves_configuration_order_for_prefix_targets(self):
        value = raw()
        variant = copy.deepcopy(value['benchmark_results'][0])
        variant.update(id='variant-case', target='gfx950-variant')
        value['benchmark_results'].append(variant)

        self.assert_ok(self.invoke([value]))
        run = self.read('runs/default-branch/attempt-1.json')
        self.assertEqual(
            [config['target'] for config in run['configurations']],
            ['gfx950', 'gfx950-variant'],
        )
        before = self.snapshot()
        value['benchmark_results'].reverse()
        self.assert_ok(self.invoke([value]))
        self.assertEqual(self.snapshot(), before)

    def test_source_revision_does_not_change_environment_identity(self):
        self.assert_ok(self.invoke())
        first = self.read('runs/default-branch/attempt-1.json')
        value = raw()
        value['provenance']['rocjitsu'].update(
            rocjitsu_commit_sha='f' * 40,
            rocjitsu_commit_timestamp='2026-01-01T00:30:00Z',
        )
        self.assert_ok(
            self.invoke([value], run_id='attempt-2', extra=(
                '--expected-sha', 'f' * 40,
                '--workflow-commit-sha', 'e' * 40,
                '--tensile-commit-sha', '1' * 40,
            ))
        )
        second = self.read('runs/default-branch/attempt-2.json')
        for section in ('machine', 'corpus'):
            self.assertEqual(first['provenance'][section], second['provenance'][section])
        self.assertEqual(first['provenance']['rocjitsu']['rocm_sdk_version'], second['provenance']['rocjitsu']['rocm_sdk_version'])
        self.assertNotEqual(first['provenance']['rocjitsu']['rocjitsu_commit_sha'], second['provenance']['rocjitsu']['rocjitsu_commit_sha'])
        for identity in ('attempt-1', 'attempt-2'):
            self.assert_ok(subprocess.run([
                sys.executable, str(UPDATE), '--data-dir', str(self.data),
                '--run-path', f'runs/default-branch/{identity}.json',
            ], capture_output=True, text=True))
        processed = subprocess.run([
            'node', str(HERE.parents[1] / 'process-dashboard-data.mjs'), str(self.data),
        ], capture_output=True, text=True)
        self.assert_ok(processed)
        normalized = json.loads(processed.stdout)['data']['runs']
        self.assertEqual(len(normalized), 2)
        self.assertEqual(normalized[0]['environmentId'], normalized[1]['environmentId'])

    def test_same_policy_inputs_cannot_silently_overwrite_provenance(self):
        first, second = raw(), raw()
        second['benchmark_results'][0]['target'] = 'gfx1250'
        second['provenance']['machine']['cpu'] = 'Different CPU'
        result = self.invoke([first, second])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Inconsistent machine provenance', result.stderr)
        self.assertFalse(self.data.exists())

    def test_immutable_comparison_distinguishes_booleans_from_numbers(self):
        value = raw()
        value['benchmark_results'][0]['problem'] = {'flag': False}
        self.assert_ok(self.invoke([value]))
        run = self.read('runs/default-branch/attempt-1.json')
        catalog = self.read(run['benchmark_catalog'])
        catalog['benchmark_definitions']['case-1']['problem']['flag'] = 0
        (self.data / run['benchmark_catalog']).write_text(json.dumps(catalog))
        before = self.snapshot()
        result = self.invoke([value])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Immutable resource conflict', result.stderr)
        self.assertEqual(before, self.snapshot())


@pytest.fixture
def identity_producer():
    spec = importlib.util.spec_from_file_location('identity_preparer', SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize_identity(producer, inputs, **changes):
    return producer.normalize_runs(inputs, **{
        'run_id': 'identity', 'branch': 'develop', 'commit_message': 'Fictional',
        'machine_id': 'fixture', 'trigger': 'manual', 'workflow_commit_sha': 'c' * 40,
        'tensile_commit_sha': 'd' * 40, **changes})


@pytest.mark.parametrize('first,last', [(1, 1.0), (1.0, 1), (0, -0.0), (-0.0, 0)])
def test_numeric_identity_collector_preserves_original_values(identity_producer, first, last):
    p = identity_producer
    value = raw()
    row = value['benchmark_results'][0]
    row['problem'] = {'nested': [first, {'fraction': 1.25, 'null': None, 'text': '1e0'}]}
    other = copy.deepcopy(row)
    other.update(target='gfx1250', problem={'nested': [last, {'text': '1e0', 'null': None, 'fraction': 1.25}]})
    value['benchmark_results'].append(other)
    snapshot = p.canonical(value)
    run, catalog = normalize_identity(p, [value])
    actual = catalog['benchmark_definitions']['case-1']['problem']['nested'][0]
    assert type(actual) is type(last)
    assert actual == last
    if actual == 0: assert math.copysign(1, actual) == math.copysign(1, last)
    assert p.canonical(value) == snapshot
    assert run['provenance'] == {**value['provenance'],
        'rocjitsu': {**value['provenance']['rocjitsu'], 'workflow_commit_sha': 'c' * 40},
        'auxiliary': {'tensile_commit_sha': 'd' * 40}}
    prepared = run['configurations'][0]['benchmark_results'][0]
    assert prepared['timing_results_s'] == [1, 9, 2]
    prepared['timing_results_s'].append(7)
    assert row['timing_results_s'] == [1, 9, 2]
    assert run['configurations'][1]['benchmark_results'][0]['timing_results_s'] == [1, 9, 2]


@pytest.mark.parametrize('left,right,equal', [
    (1, 1.0, True), (0, -0.0, True), (1.25, 1.250, True),
    ({'a': [1, None], 'b': False}, {'b': False, 'a': [1.0, None]}, True),
    (True, 1, False), (False, 0, False), ('1', 1, False), (None, 'null', False),
    (1.25, 1.5, False), (1, 2, False), ([1, 2], [2, 1], False),
    ([1], [1, 2], False), ({'a': 1}, {'b': 1}, False),
])
def test_numeric_identity_provenance_typed_matrix(identity_producer, left, right, equal):
    p = identity_producer
    first, second = raw(), raw()
    first['provenance']['auxiliary'] = {'value': left}
    second['provenance']['auxiliary'] = {'value': right}
    snapshot = p.canonical([first, second])
    if equal:
        p.validate_consistency([first, second])
        second['execution_summary']['samples'] = 4
        with pytest.raises(ValueError, match='^Inconsistent samples across raw runs$'):
            p.validate_consistency([first, second])
        second['execution_summary']['samples'] = 3
    else:
        with pytest.raises(ValueError, match='^Inconsistent auxiliary provenance across raw runs$'):
            p.validate_consistency([first, second])
    assert p.canonical([first, second]) == snapshot


@pytest.mark.parametrize('equivalent', [True, False])
def test_numeric_identity_duplicate_still_precedes_cardinality(identity_producer, equivalent):
    first, second = raw(), raw()
    second['benchmark_results'][0]['problem']['size'] = 8.0 if equivalent else True
    expected = 'Duplicate result identity' if equivalent else 'Conflicting workload definition'
    with pytest.raises(ValueError, match=expected):
        normalize_identity(identity_producer, [first, second], workflow_commit_sha='bad')


@pytest.mark.parametrize('field,invalid,error,message', [
    ('status', None, KeyError, 'status'), ('timing_results_s', 1, TypeError, 'not iterable'),
    ('error', None, KeyError, 'error'),
])
def test_numeric_identity_row_error_before_later_duplicate(identity_producer, field, invalid, error, message):
    first = raw()
    if invalid is None: del first['benchmark_results'][0][field]
    else: first['benchmark_results'][0][field] = invalid
    with pytest.raises(error, match=message):
        normalize_identity(identity_producer, [first, raw()], workflow_commit_sha='bad')


def test_numeric_identity_module_error_and_operand_order(identity_producer, tmp_path):
    p = identity_producer
    for values in ([], [raw(), raw('default')]):
        with pytest.raises(ValueError, match='^Expected one consolidated raw execution$'):
            normalize_identity(p, values, workflow_commit_sha='bad')
    empty = raw()
    empty['benchmark_results'] = []
    empty_run, empty_catalog = normalize_identity(p, [empty])
    assert empty_run['configurations'] == [] and empty_catalog['benchmark_definitions'] == {}
    first, second = raw(), raw()
    del first['benchmark_results'][0]['suite']
    second['benchmark_results'][0]['problem']['size'] = float('nan')
    with pytest.raises(KeyError, match='suite'):
        normalize_identity(p, [first, second])
    with pytest.raises(ValueError, match='workflow_commit_sha must be a full 40-hex SHA'):
        normalize_identity(p, [raw()], workflow_commit_sha='bad')
    for bad, category in [(object(), TypeError), (float('nan'), ValueError), (float('inf'), ValueError)]:
        value = raw()
        value['benchmark_results'][0]['problem'] = {'bad': bad}
        with pytest.raises(category): normalize_identity(p, [value])
    # Actual canonical operands must both complete before any comparison decoding.
    first, second = raw(), raw()
    first['provenance']['machine']['bad'] = object()
    second['provenance']['machine']['bad'] = float('nan')
    with pytest.raises(TypeError): p.validate_consistency([first, second])
    first['provenance']['machine'].pop('bad')
    with pytest.raises(ValueError, match='Out of range float values'): p.validate_consistency([first, second])
    path = tmp_path / 'existing.json'
    path.write_text('not JSON')
    with pytest.raises(json.JSONDecodeError): p.write_json(path, object())
    path.write_text('{}')
    with pytest.raises(TypeError): p.write_json(path, object())
    run, catalog = normalize_identity(p, [raw()])
    run['bad'] = object()
    with patch.object(p, 'read_json', side_effect=AssertionError('must not read')):
        with pytest.raises(TypeError): p.write_built_run(tmp_path, run, catalog)
    assert p.canonical((1, 2)) == '[1,2]'
    deep = 1.0
    for _ in range(100): deep = [deep]
    first['provenance']['machine'] = {'deep': deep}
    second['provenance']['machine'] = {'deep': copy.deepcopy(deep)}
    p.validate_consistency([first, second])


def test_numeric_identity_atomic_writer_preserves_equal_bytes(identity_producer, tmp_path):
    p = identity_producer
    path = tmp_path / 'value.json'
    original = b'{ "z": -0.0, "nested": [1e0, {"b":null,"a":false}] }\n'
    path.write_bytes(original)
    candidate = {'nested': [1, {'a': False, 'b': None}], 'z': 0}
    with patch.object(p.os, 'replace', side_effect=AssertionError('equivalent rewrite')):
        p.write_json(path, candidate)
    assert path.read_bytes() == original
    candidate['z'] = 2
    with patch.object(p.os, 'replace', wraps=p.os.replace) as replace:
        p.write_json(path, candidate)
        assert replace.call_count == 1
    assert json.loads(path.read_text()) == candidate


@pytest.mark.parametrize('conflict', ['none', 'catalog', 'run'])
def test_numeric_identity_immutable_preflight_no_partial_write(identity_producer, tmp_path, conflict):
    p = identity_producer
    run, catalog = normalize_identity(p, [raw()])
    # Seed independently with source formatting and numeric spelling, not writer output.
    paths = [(tmp_path / run['benchmark_catalog'], catalog), (tmp_path / p.run_filename(run), run)]
    for path, value in paths:
        if conflict == 'catalog' and path == paths[1][0]: continue
        if conflict == 'run' and path == paths[0][0]: continue
        seeded = copy.deepcopy(value)
        if path == paths[0][0]:
            seeded['benchmark_definitions']['case-1']['problem']['size'] = True if conflict == 'catalog' else 8.0
        else:
            seeded['execution_summary']['wall_time_s'] = 61 if conflict == 'run' else 60.0
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(seeded, indent=3, sort_keys=False) + '\n\n')
    before = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob('*.json')}
    with patch.object(p.os, 'replace', side_effect=AssertionError('must not replace')):
        if conflict == 'none': p.write_built_run(tmp_path, run, catalog)
        else:
            with pytest.raises(ValueError, match='^Immutable resource conflict:'):
                p.write_built_run(tmp_path, run, catalog)
    assert {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob('*.json')} == before


@pytest.mark.parametrize('token', ['9007199254740993', '9007199254740993.0', '9.007199254740993e15',
    '9007199254740991.00000000000000000000000000001', '1e-400', 'NaN', 'Infinity'])
def test_numeric_identity_invalid_tokens_not_coerced(identity_producer, tmp_path, token):
    path = tmp_path / 'invalid.json'
    path.write_text('{"value":' + token + '}')
    with pytest.raises(ValueError):
        identity_producer.validate_numeric_values(identity_producer.read_json(path))


def test_numeric_identity_token_and_module_api_preserved(identity_producer, tmp_path):
    p = identity_producer
    path = tmp_path / 'valid.json'
    path.write_text('[9007199254740991,-0,-0.0,0e0,5e-324,1.25]')
    parsed = p.read_json(path)
    p.validate_numeric_values(parsed)
    assert type(parsed[0]) is int and parsed[0] == 9007199254740991
    assert type(parsed[1]) is int and parsed[1] == 0
    assert type(parsed[2]) is float and math.copysign(1, parsed[2]) == -1
    assert parsed[3:] == [0.0, 5e-324, 1.25]
    assert p.canonical(parsed) == '[9007199254740991,0,-0.0,0.0,5e-324,1.25]'
    copied = tmp_path / 'standalone.py'
    copied.write_bytes(SCRIPT.read_bytes())
    with patch('subprocess.run', side_effect=AssertionError('import time I/O')):
        namespace = runpy.run_path(str(copied))
    for name in ('canonical', 'normalize_runs', 'load_pinned_manifest', 'write_json', 'write_built_run', 'prepare'):
        assert callable(namespace[name])
    assert namespace['canonical']({2: (1, 2)}) == '{"2":[1,2]}'


def test_numeric_identity_prepare_error_precedence(identity_producer, tmp_path):
    p = identity_producer
    def prepare(paths):
        return p.prepare(paths, data_dir=tmp_path / 'output', run_id='order', expected_sha=SHA,
            expected_corpus_sha=CORPUS, corpus_dir=tmp_path / 'absent-corpus', manifest='suite.toml',
            machine_id='fixture', branch='develop', commit_message='Fictional', trigger='manual',
            workflow_commit_sha='bad', tensile_commit_sha='bad')
    first, second = tmp_path / 'first.json', tmp_path / 'second.json'
    first.write_text('{}')
    second.write_text('not JSON')
    with pytest.raises(json.JSONDecodeError): prepare([first, second])
    second.write_text(json.dumps(raw()))
    with pytest.raises(KeyError, match='execution_summary'): prepare([first, second])
    one, two = raw(), raw()
    two['execution_summary']['samples'] = 4
    first.write_text(json.dumps(one))
    second.write_text(json.dumps(two))
    with pytest.raises(ValueError, match='^Inconsistent samples across raw runs$'):
        prepare([first, second])
    two['provenance']['machine']['cpu'] = 'different'
    second.write_text(json.dumps(two))
    with pytest.raises(ValueError, match='^Inconsistent machine provenance across raw runs$'):
        prepare([first, second])
    assert not (tmp_path / 'output').exists()


def test_numeric_identity_serialization_only_writer_contract(identity_producer, tmp_path):
    p = identity_producer
    missing = tmp_path / 'missing.json'
    with patch.object(p, 'canonical', side_effect=AssertionError('missing path must not canonicalize')):
        p.write_json(missing, {'tuple': (1, 2)})
    assert missing.read_text() == '{\n  "tuple": [\n    1,\n    2\n  ]\n}\n'
    # The temporary decoder is NOT a new numeric validator for incidental module paths.
    missing.write_text('{"large":1e30}')
    with patch.object(p, 'read_json', return_value={'large': 1e30}):
        with patch.object(p.os, 'replace', side_effect=AssertionError('equal unsupported module value')):
            p.write_json(missing, {'large': 1e30})


# The optional export is fictional test data for the workflow's standalone validator.
# It is never used by the benchmark publication job.
def test_export_prepared_data_for_workflow(tmp_path):
    single, multi = raw(), raw('default')
    for value in (single, multi):
        value['benchmark_results'][0]['problem']['nested'] = {'values': [1, 'literal', True]}
        for status in ('failed', 'timeout'):
            result = copy.deepcopy(value['benchmark_results'][0])
            result.update(
                id=status,
                name=status,
                status=status,
                exit_code=None,
                error='Fictional diagnostic',
                timing_results_s=[],
            )
            value['benchmark_results'].append(result)
    for samples in ([4503599627370495, 4503599627370495], [1.25], [1, 1.5], [1, 1.25, 2]):
        numeric = copy.deepcopy(single['benchmark_results'][0])
        numeric.update(id=f'numeric-{len(single["benchmark_results"])}', timing_results_s=list(samples),
                       problem={'limits': [9007199254740991, -9007199254740991, 1.25, True]})
        single['benchmark_results'].append(numeric)
    single['benchmark_results'].extend(multi['benchmark_results'])
    repository, corpus_sha = declare_fixture(tmp_path, [single])
    single['provenance']['corpus']['corpus_commit_sha'] = corpus_sha
    file = tmp_path / 'run.json'
    file.write_text(json.dumps(single))
    inputs = ['--raw-run', str(file)]
    destination = tmp_path / 'prepared'
    for branch, run_id in (
        ('develop', 'develop-fixture'),
        ('feature/example', 'branch-fixture'),
    ):
        build = tmp_path / f'build-{run_id}'
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                *inputs,
                '--data-dir',
                str(build),
                '--run-id',
                run_id,
                '--expected-sha',
                SHA,
                '--workflow-commit-sha', 'c' * 40,
                '--tensile-commit-sha', 'd' * 40,
                '--expected-corpus-sha',
                corpus_sha,
                '--corpus-dir', str(repository), '--manifest', 'suite.toml',
                '--machine-id',
                'fictional-worker',
                '--trigger',
                'manual',
                '--branch',
                branch,
                '--commit-message',
                'Fictional fixture',
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert not (build / 'index.json').exists()
        assert not (build / 'metadata.json').exists()
        run_dir = 'default-branch' if branch == 'develop' else 'side-branches'
        run_path = f'runs/{run_dir}/{run_id}.json'
        run = json.loads((build / run_path).read_text())
        for candidate in (Path(run_path), Path(run['benchmark_catalog'])):
            target = destination / candidate
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(build / candidate, target)
        result = subprocess.run(
            [
                sys.executable,
                str(UPDATE),
                '--data-dir',
                str(destination),
                '--run-path',
                run_path,
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
    index = json.loads((destination / 'index.json').read_text())
    assert len(index['runFiles']) == 2
    assert index['runFiles'] == [
        'runs/default-branch/develop-fixture.json',
        'runs/side-branches/branch-fixture.json',
    ]
    assert 'schemaVersion' not in index
    assert not (destination / 'metadata.json').exists()
    result = subprocess.run(
        [
            'node',
            str(HERE.parent.parent / 'validate-dashboard-data.mjs'),
            str(destination),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    if output := os.environ.get('DASHBOARD_VALIDATION_DIR'):
        shutil.copytree(destination, output)


if __name__ == '__main__':
    raise SystemExit(
        subprocess.call(
            [
                sys.executable,
                '-m',
                'pytest',
                str(Path(__file__).resolve()),
                *sys.argv[1:],
            ]
        )
    )
