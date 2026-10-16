# Copyright (c) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: MIT
"""Execute actual workflow discovery only, never the publisher or a Git push."""
import os
from pathlib import Path
import subprocess
import textwrap

import pytest

WORKFLOW = Path(__file__).resolve().parents[7] / '.github/workflows/rocjitsu-benchmarks.yml'


@pytest.mark.parametrize('names,accepted', [
    (['Suite.v1'], True),
    (['.Suite.v1'], True),
    (['...'], True),
    ([], False),
    (['Suite.v1', 'Other'], False),
    (['Suite.v1', '.Suite.v1'], False),
], ids=['ordinary', 'leading-dot', 'three-dots', 'empty', 'multiple-visible', 'mixed-visible-hidden'])
def test_workflow_discovers_exactly_one_literal_catalog(tmp_path, names, accepted):
    catalogs = tmp_path / 'test-catalogs'
    catalogs.mkdir()
    for name in names:
        (catalogs / f'{name}.json').write_text('{}\n')
    text = WORKFLOW.read_text(encoding='utf-8')
    # Include option setup/teardown around the actual authored expansion. Stop
    # before publisher invocation: no credentials, commits or push can execute.
    block = text.split('"${PREPARE_ARGS[@]}"', 1)[1].split(
        '          bash "${SCRIPTS_DIR}/dashboard-data/publish-dashboard-run.sh"', 1
    )[0]
    assert 'CATALOGS=(' in block and 'CATALOG_PATH=' in block
    assert 'publish-dashboard-run.sh' not in block
    script = 'set -euo pipefail\nshopt -u dotglob nullglob\n' + textwrap.dedent(block)
    script += '\nprintf "%s\\n" "${CATALOG_PATH}"\n'
    result = subprocess.run(['bash', '-c', script], env={**os.environ, 'BUILD_DIR': str(tmp_path)},
                            capture_output=True, text=True)
    assert result.returncode == (0 if accepted else 1), result.stdout + result.stderr
    assert not result.stderr
    if accepted:
        assert result.stdout == f'test-catalogs/{names[0]}.json\n'
    else:
        assert 'Expected exactly one prepared test catalog.' in result.stdout
