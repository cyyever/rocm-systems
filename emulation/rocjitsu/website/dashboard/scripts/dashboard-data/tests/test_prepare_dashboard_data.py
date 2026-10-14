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


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / 'data'

    def invoke(self, inputs=None, run_id='attempt-1', extra=(), env=None):
        extra = list(extra)
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
            '--expected-corpus-sha',
            CORPUS,
            '--machine-id',
            'worker-1',
            '--trigger',
            'auto',
            '--branch',
            'develop',
            '--commit-message',
            'Example commit',
        ]
        for i, value in enumerate(inputs if inputs is not None else [raw()]):
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
        problem = {'array': [1, {'z': None, 'flag': False}], 'object': {'b': 2, 'a': 1}, 'null': None, 'text': '[1,2]'}
        value['benchmark_results'][0]['problem'] = problem
        self.assert_ok(self.invoke([value]))
        run = self.read('runs/default-branch/attempt-1.json')
        catalog = self.read(run['testCatalog'])
        self.assertEqual(catalog['tests'][0]['problem'], problem)
        self.assert_ok(subprocess.run([sys.executable, str(UPDATE), '--data-dir', str(self.data), '--run-path', 'runs/default-branch/attempt-1.json'], capture_output=True, text=True))
        processed = subprocess.run(['node', str(HERE.parents[1] / 'process-dashboard-data.mjs'), str(self.data)], capture_output=True, text=True)
        self.assert_ok(processed)
        exported = json.loads(processed.stdout)
        self.assertEqual(exported['sourceData']['catalogs'][run['testCatalog']]['tests'][0]['problem'], problem)
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
        raw_path = self.root / 'one-raw.json'
        raw_path.write_text(json.dumps(raw()))
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
                '--expected-corpus-sha',
                CORPUS,
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

    def test_preparer_runs_without_node_or_path(self):
        environment = dict(os.environ)
        environment.pop('PATH', None)
        # An empty PATH also prevents platform-default executable lookup.
        environment['PATH'] = ''
        self.assert_ok(self.invoke(env=environment))
        self.assertTrue((self.data / 'runs/default-branch/attempt-1.json').is_file())
        self.assertFalse((self.data / 'index.json').exists())

    def test_produces_schema_one_median_results(self):
        self.assert_ok(self.invoke())
        self.assertFalse((self.data / 'metadata.json').exists())
        run = self.read('runs/default-branch/attempt-1.json')
        self.assertIs(type(run['schemaVersion']), int)
        self.assertEqual(run['schemaVersion'], 1)
        self.assertFalse((self.data / 'index.json').exists())
        self.assertNotIn('schemaVersion', self.read(run['testCatalog']))
        self.assertEqual(run['source']['commit'], SHA)
        self.assertEqual(run['execution']['completedAt'], '2026-01-01T01:01:00Z')
        config = run['configurations'][0]
        self.assertEqual(config['thread_policy'], 'single')
        self.assertNotIn('threadingMode', config)
        self.assertEqual(config['results'][0]['thread_policy'], 'single')
        self.assertEqual(
            self.read(run['testCatalog'])['configurations'],
            {'gfx950/single': ['case-1']},
        )
        self.assertEqual(config['results'][0]['durationSeconds'], 2)
        self.assertEqual(config['results'][0]['error'], None)
        self.assertEqual(config['results'][0]['testId'], 'case-1')
        self.assertEqual(
            self.read(run['testCatalog'])['tests'][0]['operation'],
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
                    run['testCatalog'],
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
        catalog = self.read(run['testCatalog'])
        self.assertEqual(len(catalog['tests']), 1)
        self.assertEqual(catalog['tests'][0]['id'], 'gemm-and-reduce.default')
        self.assertEqual(
            catalog['tests'][0]['operation'],
            'Matrix multiplication followed by reduction',
        )
        configs = {(c['target'], c['thread_policy']): c for c in run['configurations']}
        self.assertEqual(
            set(configs),
            {('gfx950', 'default'), ('gfx950', 'single'), ('gfx1250', 'default')},
        )
        for result in value['benchmark_results']:
            prepared = configs[result['target'], result['thread_policy']]['results'][0]
            self.assertEqual(prepared['thread_policy'], result['thread_policy'])
            self.assertEqual(prepared['testId'], result['id'])
            self.assertEqual(prepared['timing_results_s'], result['timing_results_s'])
            self.assertEqual(prepared['status'], result['status'])
            self.assertEqual(
                prepared['durationSeconds'],
                2 if result['status'] == 'completed' else None,
            )
        details = {entry['key']: entry['value'] for entry in run['environment']}
        self.assertEqual(details['execution.benchmark_suite'], 'performance-v1')
        self.assertEqual(details['execution.samples'], 3)
        self.assertFalse(
            any('threading_mode' in key or 'target_config' in key for key in details)
        )
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
            [test['id'] for test in self.read(run['testCatalog'])['tests']],
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
            self.read(run['testCatalog'])['configurations'],
            {f'{target}/{policy}': ['case-1'] for target, policy in pairs},
        )
        for config in run['configurations']:
            self.assertEqual(
                config['results'][0]['thread_policy'], config['thread_policy']
            )
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
            self.assertEqual(config['results'][0]['testId'], 'case-1')
            self.assertEqual(
                config['results'][0]['thread_policy'], config['thread_policy']
            )
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
                    self.assertIn(
                        'Conflicting workload definition: case-1', result.stderr
                    )
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
        details = {entry['key']: entry['value'] for entry in run['environment']}
        self.assertEqual(details['rocjitsu.rocm_sdk_version'], 'null')

    def test_same_policy_disjoint_targets_can_be_prepared_without_hash_checks(self):
        first, second = raw(), raw()
        second['benchmark_results'][0]['target'] = 'gfx1250'
        # Obsolete producer fields are neither required nor checked/published.
        first['provenance']['rocjitsu']['target_config_sha256'] = {'gfx950': 'unused'}
        second['provenance']['rocjitsu']['target_config_sha256'] = None
        self.assert_ok(self.invoke([first, second]))
        run = self.read('runs/default-branch/attempt-1.json')
        self.assertEqual(len(run['configurations']), 2)
        self.assertFalse(
            any('target_config_sha256' in item['key'] for item in run['environment'])
        )

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
        self.assertIn('Conflicting workload definition', result.stderr)
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
        catalog = self.read(run['testCatalog'])
        names = {test['id']: test['name'] for test in catalog['tests']}
        published = {
            names[result['testId']]: result
            for result in run['configurations'][0]['results']
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
                self.assertEqual(result['durationSeconds'], duration)
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
        self.assertEqual(run['source']['commit'], SHA)
        details = {entry['key']: entry['value'] for entry in run['environment']}
        self.assertEqual(details['corpus.corpus_commit_sha'], CORPUS)
        before = self.snapshot()
        self.assert_ok(self.invoke())
        self.assertEqual(self.snapshot(), before)

    def test_git_sha_provenance_matching_ignores_only_hex_case(self):
        single, multi = raw(), raw('default')
        single['provenance']['rocjitsu']['rocjitsu_commit_sha'] = 'Aa' * 20
        single['provenance']['corpus']['corpus_commit_sha'] = CORPUS.upper()
        self.assert_ok(
            self.invoke(
                [single, multi],
                extra=(
                    '--expected-sha',
                    SHA.upper(),
                    '--expected-corpus-sha',
                    'bB' * 20,
                ),
            )
        )
        run = self.read('runs/default-branch/attempt-1.json')
        self.assertEqual(run['source']['commit'], SHA)
        self.assertEqual(len(run['configurations']), 2)
        details = {entry['key']: entry['value'] for entry in run['environment']}
        self.assertEqual(details['corpus.corpus_commit_sha'], CORPUS)
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
            'results'
        ][0]
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['durationSeconds'], 2)
        self.assertIsNone(result['error'])

    def test_explicit_policies_share_definitions_with_asymmetric_membership(self):
        single, multi = raw(), raw('default')
        single['execution_summary']['benchmark_suite'] = 'performance-v1'
        multi['execution_summary']['benchmark_suite'] = 'performance-v1'
        single['benchmark_results'][0]['id'] = 'example'
        multi['benchmark_results'][0]['id'] = 'example'
        problem = {
            'nested': {'z': None, 'a': [1, False]},
            'nil': None,
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
        self.assert_ok(self.invoke([single, multi]))
        run = self.read('runs/default-branch/attempt-1.json')
        configs = {c['thread_policy']: c for c in run['configurations']}
        single_success = next(
            r for r in configs['single']['results'] if r['status'] == 'completed'
        )
        self.assertEqual(
            single_success['testId'], configs['default']['results'][0]['testId']
        )
        for result in configs['single']['results']:
            if result['status'] != 'completed':
                self.assertIsNone(result['durationSeconds'])
        catalog = self.read(run['testCatalog'])
        definition = next(
            t for t in catalog['tests'] if t['id'] == single_success['testId']
        )
        self.assertEqual(
            definition['problem'],
            {
                'nested': {'a': [1, False], 'z': None},
                'nil': None,
                'bool': False,
                'zero': 0,
                'text': 'value',
            },
        )
        details = {entry['key']: entry['value'] for entry in run['environment']}
        self.assertEqual(details['machine.hostname'], 'worker')
        self.assertFalse(any('target_config_sha256' in key for key in details))
        self.assertEqual(details['auxiliary.nested'], '{"a":null,"b":1}')
        self.assertFalse(
            any(
                'timestamp' in key or 'wall_time' in key
                for key in details
                if key.startswith('execution.')
            )
        )

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
        self.assertEqual(old['testCatalog'], new['testCatalog'])
        self.assertEqual(old['environment'], new['environment'])
        revised['benchmark_results'][0]['problem']['size'] = 16
        self.assert_ok(self.invoke([revised], run_id='attempt-3'))
        changed = self.read('runs/default-branch/attempt-3.json')
        self.assertNotEqual(old['testCatalog'], changed['testCatalog'])
        self.assertEqual(
            old['configurations'][0]['results'][0]['testId'],
            changed['configurations'][0]['results'][0]['testId'],
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
        self.assert_ok(self.invoke([single, multi]))
        self.assertEqual(
            self.read('runs/default-branch/attempt-1.json')['execution']['completedAt'],
            '2026-01-01T03:00:00Z',
        )
        original = self.snapshot()
        single['benchmark_results'].reverse()
        multi['benchmark_results'].reverse()
        self.assert_ok(self.invoke([multi, single]))
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
        old_run['configurations'][0]['results'] = []
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
        catalog = self.read(run['testCatalog'])
        catalog['tests'][0]['name'] = 'Corrupted orphan'
        (self.data / run['testCatalog']).write_text(json.dumps(catalog))
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

    def test_content_addressed_catalog_and_target_independent_workloads(self):
        import hashlib

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
            run['configurations'][0]['results'][0]['testId'],
            run['configurations'][1]['results'][0]['testId'],
        )
        catalog = self.read(run['testCatalog'])
        catalog_id = catalog.pop('id')
        encoded = json.dumps(
            catalog, sort_keys=True, separators=(',', ':'), ensure_ascii=True
        ).encode()
        self.assertEqual(catalog_id, 'catalog-' + hashlib.sha256(encoded).hexdigest())
        self.assertEqual(run['execution']['machine'], 'worker-1')

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
            self.invoke([value], run_id='attempt-2', extra=('--expected-sha', 'f' * 40))
        )
        second = self.read('runs/default-branch/attempt-2.json')
        self.assertEqual(first['environment'], second['environment'])
        self.assertNotEqual(first['source']['commit'], second['source']['commit'])

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
        catalog = self.read(run['testCatalog'])
        catalog['tests'][0]['problem']['flag'] = 0
        (self.data / run['testCatalog']).write_text(json.dumps(catalog))
        before = self.snapshot()
        result = self.invoke([value])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Immutable resource conflict', result.stderr)
        self.assertEqual(before, self.snapshot())


# The optional export is fictional test data for the workflow's standalone validator.
# It is never used by the benchmark publication job.
def test_export_prepared_data_for_workflow(tmp_path):
    single, multi = raw(), raw('default')
    for value in (single, multi):
        value['benchmark_results'][0]['problem']['nested'] = {'values': [1, None, True]}
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
    single['benchmark_results'].extend(multi['benchmark_results'])
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
                '--expected-corpus-sha',
                CORPUS,
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
        for candidate in (Path(run_path), Path(run['testCatalog'])):
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
