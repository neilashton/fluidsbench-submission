## Submission

- Dataset:
- Split:
- Submission ID:
- Model:

## Checklist

- [ ] I used the exact dataset and split version recorded in `submission.json`.
- [ ] I followed the published FluidsBench metric equations and dataset-specific reductions.
- [ ] My profile index contains every required test case, station, and quantity.
- [ ] `evaluation-evidence.json` was produced by the evaluation run recorded in `submission.json`.
- [ ] The evaluation reference version, code revision, command, and evidence checksum are accurate.
- [ ] The dataset version, split hash, case set, and profile ground-truth release/hash match in the submission and evidence.
- [ ] I used public evaluation data only for final evaluation, not fitting, selection, tuning, or preprocessing statistics.
- [ ] My code repository, full commit, model artifact, environment, instructions, digests, and open licences are accurate and public.
- [ ] I left `approval` absent and did not add `maintainer-validation.json`.
- [ ] I ran `python3 scripts/validate_submission.py --contributor-stage <submission-directory>` successfully.
- [ ] I have the right to publish the submitted metadata and profile values.
- [ ] I understand that maintainers may request calculation evidence before approval.

## Notes

Describe preprocessing, dimensionalisation, external pretraining, unusual metric handling, and any reproducibility limitations.
Disclose any contact with evaluation data before the final evaluation run; such use may make the result ineligible for ranking.

## Maintainer validation follow-up pull request

Complete this section only in the separate maintainer-owned validation/approval pull request.

- [ ] Scientific provenance and retained evidence have been reviewed.
- [ ] Public artifact access, digests, and licences have been reviewed.
- [ ] A maintainer validated the submitter-supplied files, hashes, required coverage, and ground-truth comparison basis.
- [ ] `maintainer-validation.json` records `submitted_data_only`, `model_execution=not_performed`, and
      `metric_recomputation=not_performed`.
- [ ] A maintainer added the validation checksum, `approval.status`, approver, approval date, and this pull-request URL.
