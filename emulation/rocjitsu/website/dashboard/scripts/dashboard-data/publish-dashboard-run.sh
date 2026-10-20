#!/usr/bin/env bash
# Copyright (c) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: MIT
# Run only in the dedicated, clean results checkout. Prepared inputs stay outside it.
set -euo pipefail
export LC_ALL=C

BUILD_DIR=$1
RUN_PATH=$2
CATALOG_PATH=$3
RESULTS_BRANCH=$4
COMMIT_MESSAGE=$5
SCRIPTS_DIR=$6
DIAGNOSTICS_DIR=$7
DATA_DIR="${PWD}/rocjitsu-dashboard/data"

[[ "${RUN_PATH}" =~ ^runs/(default-branch|side-branches)/[A-Za-z0-9._-]+\.json$ ]]
[[ "${CATALOG_PATH}" =~ ^test-catalogs/[A-Za-z0-9._-]+\.json$ ]]
git check-ref-format "refs/heads/${RESULTS_BRANCH}"
if [[ -n "$(git status --porcelain)" ]]; then
  echo '::error::Publication requires a clean dedicated results checkout.'
  exit 1
fi
mkdir -p "${DIAGNOSTICS_DIR}"

for ATTEMPT in 1 2 3; do
  # Repeat immutability/symlink guards after every branch reload.
  for PATH_COMPONENT in \
    "${PWD}/rocjitsu-dashboard" "${DATA_DIR}" "${DATA_DIR}/index.json" \
    "${DATA_DIR}/runs" "$(dirname "${DATA_DIR}/${RUN_PATH}")" \
    "${DATA_DIR}/${RUN_PATH}" "${DATA_DIR}/test-catalogs" \
    "${DATA_DIR}/${CATALOG_PATH}"; do
    if [[ -L "${PATH_COMPONENT}" ]]; then
      echo "::error::Dashboard publication path is a symbolic link: ${PATH_COMPONENT}"
      exit 1
    fi
  done
  python - "${BUILD_DIR}" "${RUN_PATH}" "${CATALOG_PATH}" "${SCRIPTS_DIR}" <<'PY' \
    2>&1 | tee "${DIAGNOSTICS_DIR}/validation-${ATTEMPT}.log"
from pathlib import Path
import runpy
import sys

root, run_path, catalog_path, scripts = sys.argv[1:]
producer = runpy.run_path(str(Path(scripts) / 'dashboard-data/prepare-dashboard-data.py'))
try:
    run = producer['read_json'](Path(root) / run_path)
    catalog = producer['read_json'](Path(root) / catalog_path)
    producer['require'](run['benchmark_catalog'] == catalog_path,
                        'Prepared benchmark_catalog must match publication path')
    suite = catalog['benchmark_suite']
    producer['require'](producer['safe_suite_name'](suite)
                        and catalog_path == f'test-catalogs/{suite}.json'
                        and run['execution_summary']['benchmark_suite'] == suite,
                        'Prepared benchmark_suite must match catalog and path')
except (ValueError, KeyError, TypeError, OSError) as error:
    sys.exit(f'error: {error}')
PY
  mkdir -p "$(dirname "${DATA_DIR}/${RUN_PATH}")" "${DATA_DIR}/test-catalogs"
  # Explicit existence checks avoid platform-dependent cp -n exit statuses.
  for INPUT_PATH in "${RUN_PATH}" "${CATALOG_PATH}"; do
    if [[ ! -e "${DATA_DIR}/${INPUT_PATH}" ]]; then
      cp "${BUILD_DIR}/${INPUT_PATH}" "${DATA_DIR}/${INPUT_PATH}"
    fi
    if ! cmp -s "${BUILD_DIR}/${INPUT_PATH}" "${DATA_DIR}/${INPUT_PATH}"; then
      echo "::error::Immutable publication conflict: ${INPUT_PATH}"
      exit 1
    fi
  done
  python "${SCRIPTS_DIR}/dashboard-data/update-dashboard-index.py" \
    --data-dir "${DATA_DIR}" --run-path "${RUN_PATH}" \
    2>&1 | tee "${DIAGNOSTICS_DIR}/index-${ATTEMPT}.log"
  node "${SCRIPTS_DIR}/validate-dashboard-data.mjs" "${DATA_DIR}" \
    2>&1 | tee "${DIAGNOSTICS_DIR}/validation-${ATTEMPT}.log"

  git add "rocjitsu-dashboard/data/index.json" \
    "rocjitsu-dashboard/data/${RUN_PATH}" "rocjitsu-dashboard/data/${CATALOG_PATH}"
  if git diff --cached --quiet; then
    echo "Dashboard run ${RUN_PATH} is already published"
    exit 0
  fi
  git commit --signoff -m "${COMMIT_MESSAGE}"
  PUSH_LOG="${DIAGNOSTICS_DIR}/push-${ATTEMPT}.log"
  if git push --porcelain origin "HEAD:refs/heads/${RESULTS_BRANCH}" > "${PUSH_LOG}" 2>&1; then
    cat "${PUSH_LOG}"
    exit 0
  fi
  cat "${PUSH_LOG}"
  # Trust only Git's machine-readable rejection for this exact destination.
  NON_FAST_FORWARD=false
  while IFS=$'\t' read -r FLAG REF SUMMARY; do
    if [[ "${FLAG}" == '!' && "${REF}" == "HEAD:refs/heads/${RESULTS_BRANCH}" \
          && ( "${SUMMARY}" == '[rejected] (fetch first)' \
            || "${SUMMARY}" == '[rejected] (non-fast-forward)' ) ]]; then
      NON_FAST_FORWARD=true
    fi
  done < "${PUSH_LOG}"
  if [[ "${NON_FAST_FORWARD}" != true ]]; then
    echo '::error::Publication failed without a confirmed non-fast-forward conflict.'
    exit 1
  fi
  if [[ "${ATTEMPT}" == 3 ]]; then
    echo '::error::Publication exhausted three push attempts; diagnostics retained.'
    exit 1
  fi
  git fetch --no-tags origin "refs/heads/${RESULTS_BRANCH}"
  # This reset is restricted to the dedicated publisher checkout, never source.
  git reset --hard FETCH_HEAD
done
