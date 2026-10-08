"""Exercise real contributor and maintainer gates without adding a result to feeds."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import validate_submission as validator
from scripts.manage_leaderboard import approval_documents, json_bytes
from reference.scoring_support import sha256_file

ROOT = Path(__file__).resolve().parents[1]


class AirfransDevIntakeTests(unittest.TestCase):
    def test_full_contributor_to_approval_and_closed_reynolds(self):
        spec = json.loads((ROOT / 'benchmark-specs/airfrans/submission-spec.json').read_text())
        manifest = validator.manifest_with_benchmark_contract(validator.load_json(validator.MANIFEST_PATH))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'benchmark-specs').symlink_to(ROOT / 'benchmark-specs', target_is_directory=True)
            folder = root / 'submissions/airfrans/dev-intake-trial'
            shutil.copytree(ROOT / 'submissions/airfrans/transolverpp-full-v1', folder)
            # Rebind a disposable copy of previously evaluated, byte-identical
            # predictions to the approved support/truth metadata. No inference,
            # numerical results, submitted source package or approval is changed.
            for name in ('submission.json', 'evaluation-evidence.json', 'discretization.json',
                         'metrics/cases.json', 'profiles/index.json'):
                path = folder / name
                value = json.loads(path.read_text())
                if 'submission_id' in value:
                    value['submission_id'] = 'dev-intake-trial'
                if 'dataset_version' in value:
                    value['dataset_version'] = spec['dataset_version']
                if 'reference_version' in value:
                    value['reference_version'] = spec['evaluation_reference_version']
                for key in ('scoring_support_release_id', 'scoring_support_manifest_sha256'):
                    if key in value:
                        value[key] = spec['scoring_support'][key.removeprefix('scoring_support_')]
                for key in ('profile_ground_truth_release_id', 'profile_ground_truth_manifest_sha256'):
                    if key in value:
                        value[key] = spec['profile_definition']['profile_ground_truth'][key.removeprefix('profile_ground_truth_')]
                path.write_bytes(json_bytes(value))
            path = folder / 'submission.json'
            rows_path = folder / 'discretization/cases.jsonl'
            rows = [json.loads(line) for line in rows_path.read_text().splitlines()]
            for row in rows:
                row['submission_id'] = 'dev-intake-trial'
            rows_path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            discretization_path = folder / 'discretization.json'
            discretization = json.loads(discretization_path.read_text())
            discretization['case_manifest']['sha256'] = sha256_file(rows_path)
            discretization_path.write_bytes(json_bytes(discretization))
            submission = json.loads(path.read_text())
            submission['dataset_version'] = spec['dataset_version']
            submission['evaluation']['reference_version'] = spec['evaluation_reference_version']
            submission['scoring_support'] = {k: spec['scoring_support'][k] for k in
                                             ('status', 'release_id', 'manifest_url', 'manifest_sha256')}
            truth = spec['profile_definition']['profile_ground_truth']
            submission['profile_data']['profile_ground_truth_release_id'] = truth['release_id']
            submission['profile_data']['profile_ground_truth_manifest_sha256'] = truth['manifest_sha256']
            for key in ('spatial_discretization', 'case_metrics'):
                submission[key]['sha256'] = sha256_file(folder / submission[key]['file'])
            evidence_path = folder / 'evaluation-evidence.json'
            evidence = json.loads(evidence_path.read_text())
            evidence['profile_index_sha256'] = sha256_file(folder / 'profiles/index.json')
            evidence['discretization_sha256'] = submission['spatial_discretization']['sha256']
            evidence['case_metrics_sha256'] = submission['case_metrics']['sha256']
            evidence_path.write_bytes(json_bytes(evidence))
            submission['evaluation']['evidence_sha256'] = sha256_file(evidence_path)
            path.write_bytes(json_bytes(submission))
            with patch.object(validator, 'ROOT', root):
                errors, stats = validator.validate_submission_file(path, manifest, contributor_stage=True)
                self.assertEqual(errors, [])
                self.assertEqual(stats, {'cases': 200, 'series': 1600})
                self.assertNotIn('approval', json.loads(path.read_text()))
                receipt, approved = approval_documents(submission, folder,
                    validated_by='Local intake test', validated_at='2026-10-07T20:00:00Z',
                    approved_by='Local intake test', approved_at='2026-10-07',
                    pull_request_url='https://github.com/neilashton/fluidsbench-submission/pull/1')
                (folder / 'maintainer-validation.json').write_bytes(json_bytes(receipt))
                path.write_bytes(json_bytes(approved))
                self.assertEqual(validator.validate_submission_file(path, manifest)[0], [])
                self.assertTrue(validator.validate_submission_file(path, manifest, contributor_stage=True)[0])
                closed = copy.deepcopy(submission)
                closed['split_id'] = 'reynolds_extrapolation'
                closed['split'] = 'Reynolds extrapolation'
                closed['case_set_id'] = 'reynolds_extrapolation'
                path.write_bytes(json_bytes(closed))
                errors = validator.validate_submission_file(path, manifest, contributor_stage=True)[0]
                self.assertTrue(any('does not define split' in e for e in errors), errors)


if __name__ == '__main__':
    unittest.main()
