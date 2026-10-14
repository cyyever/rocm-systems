# Copyright (c) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: MIT
"""Publication controls: fictional data and stubbed network command boundaries."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
WORKFLOW = HERE.parents[6] / '.github/workflows/rocjitsu-benchmarks.yml'


class GuardTests(unittest.TestCase):
    def test_manual_publication_is_explicit_opt_in_at_job_boundary(self):
        text = WORKFLOW.read_text()
        self.assertIn('publish_results:\n', text)
        self.assertIn('type: boolean\n        default: false', text)
        publish = text.split('\n  publish:', 1)[1]
        condition = publish.split('    if: ', 1)[1].splitlines()[0]
        self.assertIn("github.event_name != 'workflow_dispatch' || inputs.publish_results == true", condition)
        self.assertIn("!cancelled() && needs.benchmark.outputs.ran == 'true'", condition)
        # Execute the authored expression, not a separate model of the guard.
        expression = condition.removeprefix('${{ ').removesuffix(' }}')
        for event in ('push', 'workflow_dispatch'):
            for opt_in in (True, False):
                for ran in ('true', 'false'):
                    for cancelled in (True, False):
                        actual = expression.replace('!cancelled()', str(not cancelled))
                        actual = actual.replace('github.event_name', repr(event))
                        actual = actual.replace('needs.benchmark.outputs.ran', repr(ran))
                        actual = actual.replace('inputs.publish_results', str(opt_in))
                        actual = actual.replace('== true', '== True').replace('&&', 'and').replace('||', 'or')
                        expected = not cancelled and ran == 'true' and (event != 'workflow_dispatch' or opt_in)
                        self.assertEqual(eval(actual, {'__builtins__': {}}), expected)
        diagnostics = text.split('      - name: Upload benchmark diagnostics', 1)[1].split('\n  publish:', 1)[0]
        self.assertIn('if: always()', diagnostics)
        self.assertNotIn('publish_results', diagnostics)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        import json
        import shutil
        import sys
        from test_prepare_dashboard_data import raw, SHA, CORPUS

        self.json = json
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / 'publication'
        self.repo.mkdir()
        self.data = self.repo / 'rocjitsu-dashboard/data'
        self.data.mkdir(parents=True)
        (self.data / 'index.json').write_text(json.dumps({
            'generatedAt': '2026-01-01T00:00:00Z', 'runFiles': [],
        }))
        self.real_git = shutil.which('git')
        assert self.real_git is not None, 'Git is required for local publication tests'
        self.git('init', '-q')
        self.git('config', 'user.name', 'Publication fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        self.commit()
        self.base = self.git('rev-parse', 'HEAD').stdout.strip()
        self.built = self.root / 'built'
        self.run_path = 'runs/default-branch/attempt-1.json'
        raw_path = self.root / 'raw.json'
        raw_path.write_text(json.dumps(raw()))
        prepared = subprocess.run([
            sys.executable, str(HERE.parent / 'prepare-dashboard-data.py'),
            '--raw-run', str(raw_path), '--data-dir', str(self.built),
            '--run-id', 'attempt-1', '--expected-sha', SHA,
            '--expected-corpus-sha', CORPUS, '--machine-id', 'fixture',
            '--trigger', 'auto', '--branch', 'develop', '--commit-message', 'Fictional fixture',
        ], capture_output=True, text=True)
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        self.catalog = next((self.built / 'test-catalogs').glob('*.json')).relative_to(self.built).as_posix()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        # Only the network boundaries are simulated. No push command reaches Git.
        stub = self.bin / 'git'
        stub.write_text('''#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['COMMAND_LOG'], 'a') as log:
    log.write(json.dumps(args) + '\\n')
if args[0] == 'push':
    state = Path(os.environ['PUSH_STATE'])
    attempt = int(state.read_text()) if state.exists() else 0
    state.write_text(str(attempt + 1))
    outcome = json.loads(os.environ['PUSH_OUTCOMES'])[attempt]
    if outcome != 'ok':
        reason = {'conflict': 'fetch first', 'non-fast-forward': 'non-fast-forward',
                  'denied': 'remote rejected', 'network': 'connection refused'}[outcome]
        flag = '[rejected]' if outcome in ('conflict', 'non-fast-forward') else '[remote rejected]'
        if outcome == 'network':
            print('fatal: connection refused')
        else:
            print('!\\tHEAD:refs/heads/gh-pages-rocjitsu\\t' + flag + ' (' + reason + ')')
        sys.exit(1)
    print('*\\tHEAD:refs/heads/gh-pages-rocjitsu\\t[new branch]')
    sys.exit(0)
if args[0] == 'fetch':
    sys.exit(subprocess.call([os.environ['REAL_GIT'], 'update-ref', 'FETCH_HEAD', os.environ['REMOTE_HEAD']]))
sys.exit(subprocess.call([os.environ['REAL_GIT'], *args]))
''')
        stub.chmod(0o755)
        self.log = self.root / 'commands.jsonl'
        self.env = {**os.environ, 'PATH': f'{self.bin}:{os.environ["PATH"]}',
                    'REAL_GIT': self.real_git, 'COMMAND_LOG': str(self.log),
                    'PUSH_STATE': str(self.root / 'push-state'), 'LC_ALL': 'C'}
        self.helper = HERE.parent / 'publish-dashboard-run.sh'

    def git(self, *args):
        return subprocess.run([self.real_git, *args], cwd=self.repo,
                              capture_output=True, text=True, check=True)

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-qm', 'Fictional publication fixture')

    def peer(self, identity='attempt-2', conflict=False):
        import shutil
        run = self.json.loads((self.built / self.run_path).read_text())
        run['id'] = identity
        if conflict:
            run['source']['commitMessage'] = 'Conflicting immutable content'
        peer_path = f'runs/default-branch/{identity}.json'
        (self.data / peer_path).parent.mkdir(parents=True, exist_ok=True)
        (self.data / peer_path).write_text(self.json.dumps(run) + '\n')
        if identity == 'attempt-1' and not conflict:
            shutil.copyfile(self.built / self.run_path, self.data / peer_path)
        (self.data / self.catalog).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.built / self.catalog, self.data / self.catalog)
        result = subprocess.run(['python', str(HERE.parent / 'update-dashboard-index.py'),
                                 '--data-dir', str(self.data), '--run-path', peer_path],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.commit()
        remote = self.git('rev-parse', 'HEAD').stdout.strip()
        self.git('reset', '--hard', self.base)
        return remote

    def publish(self, outcomes, remote=None):
        self.assertTrue(self.helper.exists(), 'Bounded publication helper is missing')
        return subprocess.run([
            'bash', str(self.helper), str(self.built), self.run_path, self.catalog,
            'gh-pages-rocjitsu', 'Publish fictional fixture', str(HERE.parents[1]),
            str(self.root / 'diagnostics'),
        ], cwd=self.repo, env={**self.env, 'PUSH_OUTCOMES': self.json.dumps(outcomes),
                              'REMOTE_HEAD': remote or self.base},
            capture_output=True, text=True)

    def commands(self, command):
        return [row for line in self.log.read_text().splitlines()
                if (row := self.json.loads(line))[0] == command]

    def test_distinct_concurrent_publication_is_preserved(self):
        remote = self.peer()
        result = self.publish(['conflict', 'ok'], remote)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        index = self.json.loads((self.data / 'index.json').read_text())
        self.assertEqual(set(index['runFiles']), {self.run_path, 'runs/default-branch/attempt-2.json'})
        self.assertEqual(len(self.commands('push')), 2)
        self.assertEqual(len(self.commands('fetch')), 1)
        self.assertEqual((self.data / self.run_path).read_bytes(), (self.built / self.run_path).read_bytes())

    def test_identical_concurrent_publication_is_idempotent(self):
        remote = self.peer('attempt-1')
        result = self.publish(['non-fast-forward'], remote)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(self.commands('push')), 1)
        self.assertEqual(len(self.commands('commit')), 1)
        self.assertEqual(self.git('rev-parse', 'HEAD').stdout.strip(), remote)
        self.assertIn('already published', result.stdout)

    def test_conflicting_run_fails_without_another_push(self):
        remote = self.peer('attempt-1', conflict=True)
        result = self.publish(['conflict'], remote)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Immutable publication conflict', result.stdout)
        self.assertEqual(len(self.commands('push')), 1)
        self.assertEqual(self.git('rev-parse', 'HEAD').stdout.strip(), remote)
        self.assertIn('Conflicting immutable content', (self.data / self.run_path).read_text())

    def test_remote_rejection_does_not_retry(self):
        result = self.publish(['denied'])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.commands('push')), 1)
        self.assertEqual(len(self.commands('fetch')), 0)

    def test_network_failure_does_not_retry(self):
        result = self.publish(['network'])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.commands('push')), 1)
        self.assertEqual(len(self.commands('fetch')), 0)

    def test_validation_failure_does_not_commit_or_push(self):
        (self.built / self.run_path).write_text('{}')
        result = self.publish([])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.commands('push')), 0)
        self.assertEqual(len(self.commands('commit')), 0)
        self.assertTrue((self.root / 'diagnostics/validation-1.log').exists())

    def test_recovery_validates_entire_index(self):
        remote = self.peer()
        self.git('reset', '--hard', remote)
        (self.data / 'runs/default-branch/attempt-2.json').write_text('{}')
        self.commit()
        invalid_remote = self.git('rev-parse', 'HEAD').stdout.strip()
        self.git('reset', '--hard', self.base)
        result = self.publish(['conflict'], invalid_remote)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('attempt-2.json', result.stdout)
        self.assertEqual(len(self.commands('push')), 1)
        self.assertEqual(len(self.commands('commit')), 1)

    def test_exhaustion_is_three_pushes_and_retains_diagnostics(self):
        result = self.publish(['conflict', 'non-fast-forward', 'conflict'], self.peer())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('exhausted three push attempts', result.stdout)
        self.assertEqual(len(self.commands('push')), 3)
        self.assertEqual(len(self.commands('fetch')), 2)
        for attempt in (1, 2, 3):
            self.assertTrue((self.root / f'diagnostics/push-{attempt}.log').exists())
            self.assertTrue((self.root / f'diagnostics/validation-{attempt}.log').exists())
        index = self.json.loads((self.data / 'index.json').read_text())
        self.assertEqual(set(index['runFiles']), {self.run_path, 'runs/default-branch/attempt-2.json'})

    def test_second_conflict_can_succeed_on_third_attempt(self):
        result = self.publish(['conflict', 'non-fast-forward', 'ok'], self.peer())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(self.commands('push')), 3)
        self.assertEqual(len(self.commands('fetch')), 2)

    def test_conflicting_catalog_fails_before_push(self):
        remote = self.peer()
        self.git('reset', '--hard', remote)
        (self.data / self.catalog).write_text('{}')
        self.commit()
        remote = self.git('rev-parse', 'HEAD').stdout.strip()
        self.git('reset', '--hard', self.base)
        result = self.publish(['conflict'], remote)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Immutable publication conflict: test-catalogs/', result.stdout)
        self.assertEqual(len(self.commands('push')), 1)

    def test_symlink_index_is_rejected(self):
        target = self.root / 'outside-index.json'
        target.write_text((self.data / 'index.json').read_text())
        (self.data / 'index.json').unlink()
        (self.data / 'index.json').symlink_to(target)
        self.commit()
        result = self.publish([])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('symbolic link', result.stdout)
        self.assertEqual(len(self.commands('push')), 0)


if __name__ == '__main__':
    unittest.main()
