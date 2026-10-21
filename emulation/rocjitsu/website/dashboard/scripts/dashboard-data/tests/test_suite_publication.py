# Copyright (c) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: MIT
"""Frozen-source CLI acceptance, using fictional timings and real consumer tools."""
import copy
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest
from manifest_fixture import declare_fixture

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / 'prepare-dashboard-data.py'
SHA = 'a' * 40


def fixture_input(ids=('a', 'b'), name='Suite.v1', day=1):
    return {
        'execution_summary': {'benchmark_suite': name, 'warmups': 0, 'samples': 1,
                              'timeout_seconds': 60, 'timestamp': f'2026-01-{day:02}T01:00:00Z',
                              'finished_at': f'2026-01-{day:02}T02:00:00Z', 'wall_time_s': 1},
        'provenance': {'machine': dict(hostname='fixture', platform='Linux', kernel='fixture', cpu='fictional'),
                       'rocjitsu': {'rocjitsu_commit_sha': SHA, 'rocjitsu_commit_timestamp': '2025-01-01T00:00:00Z', 'rocm_sdk_version': None},
                       'corpus': {'corpus_commit_sha': 'b' * 40, 'corpus_commit_timestamp': '2025-01-01T00:00:00Z'}, 'auxiliary': {}},
        'benchmark_results': [{'id': identity, 'suite': 'Triton', 'name': identity, 'operation': 'Compute',
                               'problem': {'shape': [1, 2], 'options': {'transpose': False}},
                               'target': 'gfx950', 'thread_policy': 'default', 'status': 'completed',
                               'timing_results_s': [index + 1], 'exit_code': 0, 'error': None}
                              for index, identity in enumerate(ids)],
    }


def bind(raw, root):
    repo, sha = declare_fixture(root, [raw])
    raw['provenance']['corpus']['corpus_commit_sha'] = sha
    return repo, sha


def invoke(root, raw_inputs, repo, sha, output=None, run_id='attempt', extra=()):
    output = output or root / 'output'
    args = [sys.executable, str(SCRIPT), '--data-dir', str(output), '--run-id', run_id,
            '--workflow-commit-sha', 'c' * 40, '--tensile-commit-sha', 'd' * 40,
            '--expected-sha', SHA, '--expected-corpus-sha', sha, '--corpus-dir', str(repo),
            '--manifest', 'suite.toml', '--machine-id', 'fixture', '--branch', 'develop',
            '--trigger', 'manual', '--commit-message', 'Fictional source-boundary test']
    for index, value in enumerate(raw_inputs):
        file = root / f'raw-{index}.json'
        file.write_text(json.dumps(value))
        args.extend(['--raw-run', str(file)])
    return subprocess.run(args + list(extra), capture_output=True, text=True)


def inventory(output):
    return {p.relative_to(output).as_posix(): p.read_bytes() for p in output.rglob('*') if p.is_file()}


def assert_ok(result):
    assert result.returncode == 0, result.stdout + result.stderr


def index_and_process(output, run_ids):
    for identity in run_ids:
        assert_ok(subprocess.run([sys.executable, str(HERE.parent / 'update-dashboard-index.py'), '--data-dir', str(output),
                                  '--run-path', f'runs/default-branch/{identity}.json'], capture_output=True, text=True))
    assert_ok(subprocess.run(['node', str(HERE.parents[1] / 'validate-dashboard-data.mjs'), str(output)], capture_output=True, text=True))
    result = subprocess.run(['node', str(HERE.parents[1] / 'process-dashboard-data.mjs'), str(output)], capture_output=True, text=True)
    assert_ok(result)
    return json.loads(result.stdout)


def test_full_failure_membership_idempotence_and_actual_consumer(tmp_path):
    value = fixture_input()
    repo, sha = bind(value, tmp_path)
    value['benchmark_results'][1].update(status='timeout', error='Fictional timeout', exit_code=None)
    assert_ok(invoke(tmp_path, [value], repo, sha))
    original = inventory(tmp_path / 'output')
    assert_ok(invoke(tmp_path, [value], repo, sha))
    assert inventory(tmp_path / 'output') == original
    value['benchmark_results'].reverse()
    assert_ok(invoke(tmp_path, [value], repo, sha))
    assert inventory(tmp_path / 'output') == original
    for row in value['benchmark_results']:
        if row['status'] == 'completed': row['timing_results_s'] = [42]
    assert_ok(invoke(tmp_path, [value], repo, sha, run_id='timing'))
    assert (tmp_path / 'output/test-catalogs/Suite.v1.json').read_bytes() == original['test-catalogs/Suite.v1.json']
    for row in value['benchmark_results']:
        row.update(status='failed', error='Fictional interrupted placeholder', exit_code=None, timing_results_s=[])
    value['execution_summary']['samples'] = 3
    assert_ok(invoke(tmp_path, [value], repo, sha, run_id='failure'))
    assert (tmp_path / 'output/test-catalogs/Suite.v1.json').read_bytes() == original['test-catalogs/Suite.v1.json']
    parsed = index_and_process(tmp_path / 'output', ['attempt', 'failure', 'timing'])
    assert len(parsed['sourceData']['runs']) == 3
    assert parsed['sourceData']['catalogs']['test-catalogs/Suite.v1.json']['benchmark_suite'] == 'Suite.v1'
    assert all(row['status'] == 'failed' and row['timing_results_s'] == [] for row in parsed['sourceData']['runs'][1]['configurations'][0]['benchmark_results'])
    assert all(row['durationSeconds'] is None for row in next(run for run in parsed['data']['runs'] if run['runId'] == 'failure')['tests'])
    assert parsed['sourceData']['catalogs']['test-catalogs/Suite.v1.json']['benchmark_definitions']['a']['problem']['shape'] == [1, 2]


@pytest.mark.parametrize('change', ['filtered', 'deleted', 'extra', 'duplicate', 'complementary', 'definition', 'unfinished'])
@pytest.mark.parametrize('seeded', [False, True])
def test_frozen_manifest_rejects_before_any_write(tmp_path, change, seeded):
    full = fixture_input()
    repo, sha = bind(full, tmp_path)
    output = tmp_path / 'output'
    if seeded: assert_ok(invoke(tmp_path, [full], repo, sha))
    before = inventory(output)
    value = copy.deepcopy(full)
    inputs = [value]
    if change in ('filtered', 'deleted'): value['benchmark_results'].pop()
    if change == 'extra': value['benchmark_results'][0]['target'] = 'gfx999'
    if change == 'duplicate': value['benchmark_results'].append(copy.deepcopy(value['benchmark_results'][0]))
    if change == 'complementary':
        other = copy.deepcopy(value)
        value['benchmark_results'] = value['benchmark_results'][:1]
        other['benchmark_results'] = other['benchmark_results'][1:]
        inputs.append(other)
    if change == 'definition': value['benchmark_results'][0]['problem']['shape'] = '[1,2]'
    if change == 'unfinished': value['execution_summary']['finished_at'] = None
    result = invoke(tmp_path, inputs, repo, sha, run_id='rejected')
    assert result.returncode == 1
    category = 'Duplicate' if change == 'duplicate' else 'definition' if change == 'definition' else 'finished_at' if change == 'unfinished' else 'missing='
    assert category in result.stderr
    assert inventory(output) == before
    assert output.exists() == seeded


def test_changed_same_name_is_immutable_and_suite_rename_cannot_bypass_ids(tmp_path):
    value = fixture_input()
    repo, sha = bind(value, tmp_path)
    assert_ok(invoke(tmp_path, [value], repo, sha))
    before = inventory(tmp_path / 'output')
    changed = copy.deepcopy(value)
    changed['benchmark_results'][0]['problem']['shape'] = [2, 1]
    changed_repo, changed_sha = bind(changed, tmp_path)
    result = invoke(tmp_path, [changed], changed_repo, changed_sha, run_id='changed')
    assert result.returncode == 1 and 'Immutable resource conflict' in result.stderr
    assert inventory(tmp_path / 'output') == before
    changed['execution_summary']['benchmark_suite'] = 'Suite.v2'
    renamed_repo, renamed_sha = bind(changed, tmp_path)
    assert_ok(invoke(tmp_path, [changed], renamed_repo, renamed_sha, run_id='renamed'))
    # Standalone conversion succeeds; combined publication guard must still reject
    # incompatible reused workload IDs across distinct names.
    for identity in ('attempt', 'renamed'):
        assert_ok(subprocess.run([sys.executable, str(HERE.parent / 'update-dashboard-index.py'), '--data-dir', str(tmp_path / 'output'), '--run-path', f'runs/default-branch/{identity}.json'], capture_output=True, text=True))
    result = subprocess.run(['node', str(HERE.parents[1] / 'validate-dashboard-data.mjs'), str(tmp_path / 'output')], capture_output=True, text=True)
    assert result.returncode != 0 and 'defined differently' in result.stderr + result.stdout
    changed['benchmark_results'][0]['id'] = 'a-v2'
    final_repo, final_sha = bind(changed, tmp_path)
    fresh = tmp_path / 'fresh'
    assert_ok(invoke(tmp_path, [value], repo, sha, output=fresh))
    assert_ok(invoke(tmp_path, [changed], final_repo, final_sha, output=fresh, run_id='renamed'))
    assert len(index_and_process(fresh, ['attempt', 'renamed'])['data']['runs']) == 2


@pytest.mark.parametrize('name', ['../x', '/x', 'a/b', 'a\\b', ' ', '%2f', '', '.', '..'])
def test_unsafe_raw_suite_rejects_before_writes(tmp_path, name):
    value = fixture_input()
    repo, sha = bind(value, tmp_path)
    value['execution_summary']['benchmark_suite'] = name
    result = invoke(tmp_path, [value], repo, sha)
    assert result.returncode == 1 and 'benchmark_suite' in result.stderr
    assert not (tmp_path / 'output').exists()


def test_actual_prepared_three_suites_project_before_success_filtering(tmp_path):
    output = tmp_path / 'output'
    identities = []
    for day, name, members in [(1, 'A', ('a', 'b', 'c')), (2, 'B', ('a', 'b', 'd')), (3, 'C', ('a', 'c', 'd')), (4, 'A', ('a', 'b', 'c'))]:
        value = fixture_input(members, name, day)
        commit = str(day) * 40
        value['provenance']['rocjitsu'].update(rocjitsu_commit_sha=commit, rocjitsu_commit_timestamp=f'2026-01-{day:02}T00:00:00Z')
        if name == 'B':
            value['benchmark_results'].extend([{**copy.deepcopy(row), 'target': 'gfx1250'} for row in value['benchmark_results']])
        repo, sha = bind(value, tmp_path)
        if name == 'C': value['benchmark_results'][0].update(status='failed', exit_code=1, error='Fictional failure')
        identity = f'run-{day}'
        identities.append(identity)
        assert_ok(invoke(tmp_path, [value], repo, sha, output=output, run_id=identity, extra=('--expected-sha', commit)))
    parsed = index_and_process(output, identities)
    file = tmp_path / 'processed.json'
    file.write_text(json.dumps(parsed))
    projection_url = (HERE.parents[2] / 'src/data/overviewProjection.js').as_uri()
    script = '''import fs from 'node:fs';
import assert from 'node:assert/strict';
const {selectOverviewProjection} = await import(process.argv[2]);
const {data, sourceData} = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
const filters = {targets:['gfx950'], modes:['default'], suites:['Triton']};
const daily = selectOverviewProjection(data, filters, {range:'ALL'});
assert.deepEqual(daily.rows[0].cohortIds, ['a']);
assert.equal(daily.rows[0].catalogIds.length, 3);
assert.equal(daily.rows[0].points[2].durationSeconds, null);
assert.equal(daily.rows[0].points[2].reason, 'failed');
const weekly = selectOverviewProjection(data, filters, {range:'1W'});
assert.deepEqual(weekly.rows[0].cohortIds, ['a']);
assert.equal(weekly.attempts.find(a=>a.runId==='run-3').eligible, false);
assert.equal(weekly.rows[0].catalogIds.length, 3);
const withinA = selectOverviewProjection(data, filters, {range:'1D'});
assert.deepEqual(withinA.rows[0].cohortIds, ['a','b','c']);
const explicitA = selectOverviewProjection(data, filters, {range:'ALL',catalogId:'A'});
assert.deepEqual([explicitA.startDay,explicitA.anchorDay],[daily.startDay,daily.anchorDay]);
assert.deepEqual(explicitA.rows[0].cohortIds,['a','b','c']);
const absentLane = selectOverviewProjection(data, {...filters,targets:['gfx950','gfx1250']}, {range:'ALL'});
assert.equal(absentLane.rows.find(r=>r.target==='gfx1250').points[0].reason,'configuration-absent');
const empty = selectOverviewProjection(data, {...filters,suites:[]}, {range:'ALL'});
assert.deepEqual(empty.rows[0].cohortIds,[]);
const unavailable = selectOverviewProjection(data, filters,{range:'ALL',catalogId:'unknown'});
assert.equal(unavailable.latestRun,null);
assert.deepEqual(sourceData, JSON.parse(fs.readFileSync(process.argv[1],'utf8')).sourceData);
console.log('Prepared A/B/C + recurring A: intersection, period, daily failure, weekly pre-eligibility, absent lane, empty filters, fixed window and source preservation PASS');'''
    result = subprocess.run(['node', '--input-type=module', '-e', script, str(file), projection_url], capture_output=True, text=True)
    assert_ok(result)
    disconnected = fixture_input(('x',), 'D', 5)
    disconnected['provenance']['rocjitsu'].update(rocjitsu_commit_sha='5' * 40, rocjitsu_commit_timestamp='2026-01-05T00:00:00Z')
    repo, sha = bind(disconnected, tmp_path)
    assert_ok(invoke(tmp_path, [disconnected], repo, sha, output=output, run_id='run-5', extra=('--expected-sha', '5' * 40)))
    file.write_text(json.dumps(index_and_process(output, [*identities, 'run-5'])))
    empty_script = '''import fs from 'node:fs'; import assert from 'node:assert/strict';
const {selectOverviewProjection} = await import(process.argv[2]);
const {data} = JSON.parse(fs.readFileSync(process.argv[1],'utf8'));
const view = selectOverviewProjection(data,{targets:['gfx950'],modes:['default'],suites:['Triton']},{range:'ALL'});
assert.deepEqual(view.rows[0].cohortIds,[]);
assert.ok(view.rows[0].points.every(point=>point.durationSeconds===null && point.reason==='no-comparable-workloads'));
console.log('Prepared disjoint suite: empty intersection is unavailable, never zero PASS');'''
    assert_ok(subprocess.run(['node', '--input-type=module', '-e', empty_script, str(file), projection_url], capture_output=True, text=True))


def commit_numeric_pin(root, name):
    repo = root / name
    repo.mkdir()
    content = f'name = "{name}"\n'
    for identity in ('a', 'b'):
        content += f'''[[cases]]
id = "{identity}"
suite = "Triton"
name = "{identity}"
operation = "Compute"
targets = ["gfx950"]
thread_policies = ["default"]
params = {{shape = [1, 2], options = {{transpose = false}}, nested = {{value = 1, zero = 0}}}}
'''
    (repo / 'suite.toml').write_text(content)
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()
    git('init', '-q')
    git('add', 'suite.toml')
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        '-c', 'commit.gpgsign=false', 'commit', '--no-gpg-sign', '--no-signoff', '-qm', 'Independent numeric pin')
    return repo, git('rev-parse', 'HEAD')


def test_numeric_identity_actual_cli_updater_and_js_consumers(tmp_path):
    # Both explicit pins exist before constructing any candidate raw variants.
    pins = [commit_numeric_pin(tmp_path, name) for name in ('NumericA', 'NumericB')]
    output = tmp_path / 'output'
    originals = []
    for index, ((repo, sha), token) in enumerate(zip(pins, ('1', '1e0'))):
        value = fixture_input(name=repo.name, day=index + 1)
        value['provenance']['corpus']['corpus_commit_sha'] = sha
        value['provenance']['auxiliary'] = {'open': [None, False, '1e0', -0.0]}
        for row in value['benchmark_results']:
            row['problem']['nested'] = {'value': 'TOKEN', 'zero': 'ZERO'}
        value['benchmark_results'][0]['timing_results_s'] = [9, 1, 4, 2]
        value['benchmark_results'][1].update(status='failed', timing_results_s=[5, 2],
                                              error='Fictional failure', exit_code=1)
        path = tmp_path / 'numeric-raw.json'
        text = json.dumps(value).replace('"TOKEN"', token).replace('"ZERO"', '-0.0')
        path.write_text(text)
        assert '"value": ' + token in path.read_text() and '-0.0' in path.read_text()
        assert_ok(invoke(tmp_path, [], repo, sha, output=output, run_id=f'numeric-{index}',
                         extra=('--raw-run', str(path))))
        originals.append(json.loads((output / f'runs/default-branch/numeric-{index}.json').read_text()))
        before = inventory(output)
        # Equal parsed provenance, definition and summary spelling must reuse exact bytes.
        path.write_text(text.replace('"wall_time_s": 1', '"wall_time_s": 1.0')
                        .replace('"value": ' + token, '"value": 1.0'))
        assert_ok(invoke(tmp_path, [], repo, sha, output=output, run_id=f'numeric-{index}',
                         extra=('--raw-run', str(path))))
        assert inventory(output) == before
        print(json.dumps({'pin': sha, 'catalog': repo.name, 'raw_token': token, 'byte_reuse': True}))
    parsed = index_and_process(output, ['numeric-0', 'numeric-1'])
    # Parsed processor result, not raw Node stdout; JS JSON has one numeric type.
    (tmp_path / 'processed-parsed.json').write_text(json.dumps(parsed, indent=2))
    assert len(parsed['sourceData']['catalogs']) == 2 and len(parsed['data']['runs']) == 2
    assert parsed['sourceData']['runs'] == originals
    for index, run in enumerate(parsed['data']['runs']):
        assert run['runId'] == f'numeric-{index}'
        source = originals[index]
        assert source['source'] == {'branch': 'develop', 'message': 'Fictional source-boundary test'}
        assert source['provenance']['auxiliary'] == {'open': [None, False, '1e0', -0.0], 'tensile_commit_sha': 'd' * 40}
        catalog = parsed['sourceData']['catalogs'][source['benchmark_catalog']]
        assert catalog['membership'] == {'gfx950': {'default': ['a', 'b']}}
        emitted = json.loads((output / source['benchmark_catalog']).read_text())
        for identity in ('a', 'b'):
            original_problem = emitted['benchmark_definitions'][identity]['problem']
            assert type(original_problem['nested']['value']) is (int if index == 0 else float)
            assert original_problem['nested']['value'] == 1
            assert type(original_problem['nested']['zero']) is float
            assert math.copysign(1, original_problem['nested']['zero']) == -1
            problem = catalog['benchmark_definitions'][identity]['problem']
            assert type(problem['nested']['value']) in (int, float) and problem['nested']['value'] == 1
            assert type(problem['nested']['zero']) in (int, float) and problem['nested']['zero'] == 0
            assert type(problem['shape']) is list and problem['shape'] == [1, 2]
            assert all(type(v) in (int, float) for v in problem['shape'])
            assert problem['options']['transpose'] is False
        original_open = source['provenance']['auxiliary']['open']
        assert type(original_open[-1]) is float and math.copysign(1, original_open[-1]) == -1
        exported_open = parsed['sourceData']['runs'][index]['provenance']['auxiliary']['open']
        assert type(exported_open) is list and exported_open[0] is None and exported_open[1] is False
        assert type(exported_open[2]) is str and exported_open[2] == '1e0'
        assert type(exported_open[3]) in (int, float) and exported_open[3] == 0
        assert [(t['logicalTestId'], t['status'], t['timing_results_s'], t['durationSeconds']) for t in run['tests']] == [
            ('a', 'completed', [9, 1, 4, 2], 3), ('b', 'failed', [5, 2], None)]
        assert all(t['problem'] == {'shape': [1, 2], 'options': {'transpose': False},
                                   'nested': {'value': 1, 'zero': 0}} for t in run['tests'])
        for test in run['tests']:
            assert type(test['problem']['nested']['value']) in (int, float)
            assert type(test['problem']['nested']['zero']) in (int, float)
            assert test['problem']['options']['transpose'] is False
            assert all(type(v) in (int, float) for v in test['timing_results_s'])
    before = inventory(output)
    for token in ('true', '2', '"1"'):
        path.write_text(text.replace('"TOKEN"', token) if '"TOKEN"' in text else
                        text.replace('"value": 1e0', '"value": ' + token))
        result = invoke(tmp_path, [], *pins[1], output=output, run_id='rejected-' + token.replace('"', ''),
                        extra=('--raw-run', str(path)))
        assert result.returncode == 1 and 'Pinned workload definition mismatch' in result.stderr
        assert inventory(output) == before
