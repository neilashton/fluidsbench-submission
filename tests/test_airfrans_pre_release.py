"""The dev registration is byte-bound and cannot activate official intake."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from reference.airfrans.pre_release import (
    REGISTRY_PATH, candidate_validation_view, registered_airfrans_pre_release_reference,
)
from reference.ahmedml.pre_release import package_tree_binding, sha256_file

ROOT = Path(__file__).resolve().parents[1]


class AirfransPreReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        registry = json.loads((ROOT / REGISTRY_PATH).read_text())
        self.entry = copy.deepcopy(next(e for e in registry['entries'] if e['split_id'] == 'full'))
        self.path = self.root / self.entry['submission_path']
        self.path.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / self.entry['submission_path'], self.path)
        # Registration's tree primitive is tested independently from the full
        # source validator. Keep the fixture small; integration validates the
        # complete retained package and release metadata.
        self.submission = json.loads(self.path.read_text())
        self.entry['package_tree'] = package_tree_binding(self.path.parent)
        for item in self.entry['artifacts']:
            dest = self.root / item['file']
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / item['file'], dest)
        receipt_path = self.root / self.entry['validation_receipt']
        receipt = json.loads(receipt_path.read_text())
        receipt['package_tree'] = self.entry['package_tree']
        receipt_path.write_text(json.dumps(receipt))
        for item in self.entry['artifacts']:
            item['sha256'] = sha256_file(self.root / item['file'])
        snapshot = self.root / registry['contract_snapshot']['file']
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / registry['contract_snapshot']['file'], snapshot)
        registry['entries'] = [self.entry]
        self.registry = registry
        self.save_registry()
        self.spec_path = self.root / 'benchmark-specs/airfrans/submission-spec.json'
        shutil.copyfile(ROOT / 'benchmark-specs/airfrans/submission-spec.json', self.spec_path)
        self.manifest = {'data_release': {'status': 'prototype_dummy_data'}}

    def save_registry(self):
        (self.root / REGISTRY_PATH).write_text(json.dumps(self.registry))

    def binding(self):
        return registered_airfrans_pre_release_reference(
            self.path, self.submission, self.manifest, root=self.root)

    def test_feed_claim_cannot_be_promoted_or_cited(self):
        from scripts.manage_leaderboard import claim_eligibility
        claim = claim_eligibility("prototype_dummy_data", {
            "dataset_id": "airfrans", "record_type": "pre_release_reference"})
        self.assertFalse(claim["promotion"])
        self.assertFalse(claim["academic_citation"])
        self.assertIn("AirfRANS", claim["reason"])

    def test_exact_candidate_is_recognized(self):
        self.assertEqual(self.binding(), self.entry)

    def test_prediction_or_extra_file_change_invalidates_binding(self):
        (self.path.parent / 'changed-prediction.json').write_text('{}')
        self.assertIsNone(self.binding())

    def test_release_metadata_change_invalidates_binding(self):
        artifact = self.root / self.entry['artifacts'][0]['file']
        artifact.write_text(artifact.read_text() + ' ')
        self.assertIsNone(self.binding())

    def test_approval_and_official_feed_are_rejected(self):
        self.submission['approval'] = {'status': 'approved'}
        self.assertIsNone(self.binding())
        self.submission.pop('approval')
        self.manifest['data_release']['status'] = 'official'
        self.assertIsNone(self.binding())

    def test_open_historical_contract_is_rejected(self):
        snapshot = self.root / self.registry['contract_snapshot']['file']
        spec = json.loads(snapshot.read_text())
        spec['scoring_support']['submissions_open'] = True
        snapshot.write_text(json.dumps(spec))
        self.assertIsNone(self.binding())

    def test_incomplete_receipt_is_rejected_even_when_rehashed(self):
        receipt_path = self.root / self.entry['validation_receipt']
        receipt = json.loads(receipt_path.read_text())
        receipt['profile_scores_reproduced'] = False
        receipt_path.write_text(json.dumps(receipt))
        for item in self.entry['artifacts']:
            if item['file'] == self.entry['validation_receipt']:
                item['sha256'] = sha256_file(receipt_path)
        self.save_registry()
        self.assertIsNone(self.binding())

    def test_candidate_view_preserves_closed_published_contract(self):
        spec = json.loads(self.spec_path.read_text())
        original = copy.deepcopy(spec)
        view, manifest = candidate_validation_view(spec, self.manifest, self.entry, root=self.root)
        self.assertEqual(spec, original)
        self.assertNotIn('profile_ground_truth', self.manifest['data_release'])
        self.assertFalse(view['scoring_support']['submissions_open'])
        self.assertEqual(view['scoring_support']['status'], 'owner_review_required')
        self.assertEqual(manifest['data_release']['status'], 'prototype_dummy_data')


if __name__ == '__main__':
    unittest.main()
