import { fixtureRunPath } from './runPath.js';
import { createMaintainedPublication } from './maintainedDataset.js';

// Additive v11 fixture overlay; never imported by production application code.
export function createFeedbackPublication() {
  const publication = createMaintainedPublication();
  const run = structuredClone(publication.runs.find((run) => run.publication.id === 'fictional-branch-01'));
  run.publication.id = 'fictional-rattataking-test-branch';
  run.provenance.rocjitsu.rocjitsu_commit_sha = 'f1c7'.repeat(10);
  run.provenance.rocjitsu.rocjitsu_commit_timestamp = '2026-10-05T09:00:00.000Z';
  run.publication.source = { branch: 'users/RattataKing/test-branch', message: 'FICTIONAL RattataKing test branch',
    base: { branch: 'develop', commit: publication.runs.find((run) => run.publication.id === 'fictional-develop-20').provenance.rocjitsu.rocjitsu_commit_sha },
  };
  run.execution_summary.finished_at = '2026-10-05T11:20:00.000Z';
  publication.runs.push(run);
  publication.index.runFiles.push(fixtureRunPath(run));
  return publication;
}
