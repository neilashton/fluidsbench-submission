## Submission

- Dataset:
- Split:
- Submission ID:
- Model:

## Checklist

- [ ] I used the exact dataset and split version recorded in `submission.json`.
- [ ] The dataset specification marks my exact scoring-support release `official`, owner-approved, and open for submissions.
- [ ] I followed the published FluidsBench metric equations and dataset-specific reductions.
- [ ] `metrics/cases.json` covers every official case and support with complete count and weight coverage.
- [ ] `discretization.json` and `discretization/cases.jsonl` accurately report training and inference representations, counts,
      domains, direct outputs, and mappings to every scoring support.
- [ ] My profile index contains every required test case, station, and quantity.
- [ ] `evaluation-evidence.json` was produced by the evaluation run recorded in `submission.json`.
- [ ] The evaluation reference version, command, and evidence checksum are accurate; if I supplied code metadata, all matching code
      revisions are accurate.
- [ ] The dataset version, split hash, case set, scoring-support release/hash, spatial hash, per-case-metric hash, and profile
      ground-truth release/hash match throughout the package.
- [ ] I used public evaluation data only for final evaluation, not fitting, selection, tuning, or preprocessing statistics.
- [ ] If I supplied optional code, model, environment, or documentation artifacts, their revisions, digests, URLs, and licences are
      accurate and public.
- [ ] I left `approval` absent and did not add `maintainer-validation.json` or `prediction-artifact-checks.json`.
- [ ] If I declared optional prediction artifacts, each repository revision, manifest digest, support identity, split, coverage,
      and licence is accurate.
- [ ] I ran `python3 scripts/validate_submission.py --contributor-stage <submission-directory>` successfully.
- [ ] I have the right to publish the submitted metadata and profile values.
- [ ] I understand that maintainers may request calculation evidence before approval.

## Notes

Describe preprocessing, dimensionalisation, external pretraining, unusual metric handling, and any reproducibility limitations.
Disclose any contact with evaluation data before the final evaluation run; such use may make the result ineligible for ranking.

## Maintainer validation follow-up pull request

Complete this section only in the separate maintainer-owned validation/approval pull request.

- [ ] Scientific provenance and retained evidence have been reviewed.
- [ ] The result-data licence and any declared optional artifact access, digests, and licences have been reviewed.
- [ ] A maintainer validated the submitter-supplied files, hashes, required coverage, and ground-truth comparison basis.
- [ ] `maintainer-validation.json` records `submitted_data_only`, `model_execution=not_performed`, and
      `metric_recomputation=not_performed`.
- [ ] The validation record binds the scoring support, spatial report, per-case metrics, profiles, and evaluation evidence.
- [ ] A maintainer added the validation checksum, `approval.status`, approver, approval date, and this pull-request URL.
