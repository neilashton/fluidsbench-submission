# DrivAerML scientific-contract proposal

This directory preserves the reviewed scientific proposal and its audit
evidence. The participant-facing decisions have since been promoted into the
closed candidate [`../submission-spec.json`](../submission-spec.json), while
the files here remain non-activating source evidence: they do not by themselves
open submissions, activate the composite, or make historical dummy rows real.

The proposed benchmark is defined by a frozen raw-data support, not by the
representation preferred by a particular model:

- surface: every raw `boundary_<run>.vtp` `CellData` polygon;
- volume: every raw reconstructed `volume_<run>.vtu` `CellData` cell, proposed
  as the FVM-aligned carrier pending owner provenance confirmation; and
- identity: `(case_id, raw_vtk_cell_id)`, with cell centres supplied only as
  coordinates, not used as entity identity.

AB-UPT and GeoTransolver results are documented as separately named literature
tracks. They must not be compared directly with the canonical full-volume
score: AB-UPT samples volume cells, while GeoTransolver evaluates raw VTU
`PointData` vertices. An executable parity claim additionally requires every
paper-specific sampling and reduction detail to be pinned.

The proposed engineering branch reconstructs whole-vehicle force and pitch
moment from the participant's locally evaluated native surface predictions. It reports `Cd`, `Cl`,
`CmPitch`, `Clf`, and `Clr`; the composite ranks the independent `Cd`,
total-`Cl`, and
front/rear-balance modes without treating `Cl=Clf+Clr` as three independent
measurements.

On 2026-08-21 the benchmark owner removed the 209 discrete Cp probes from the
current DrivAerML submission and score, while retaining four true continuous Cp
cuts: upperbody centreline, underbody centreline, sidewall at `z=0.15 m`, and
front-left wheelhouse at `y=-0.6 m`. The submission-facing diagnostic registry
is `../drivaerml-diagnostics-v9.json`. The probe files in this proposal directory
and the generated probe evidence are retained only as inactive research
records; they are not participant requirements, scoring support, composite
components, or activation gates. Separate continuous-cut extraction and
scoring support remains an activation task.

Files:

- [`SCIENTIFIC_CONTRACT.md`](SCIENTIFIC_CONTRACT.md): review rationale and the
  proposed human-readable contract;
- [`contract-proposal.json`](contract-proposal.json): the same decisions in a
  machine-readable form;
- [`force-definition-audit-all484.json`](force-definition-audit-all484.json):
  the all-public-case coefficient closure, constant-reference, and
  moment-origin consistency audit (not a substitute for the pending all-case
  native-field replay);
- [`run-1-force-axle-replay-summary.json`](run-1-force-axle-replay-summary.json):
  the golden native-polygon force and pitch-moment replay for `Cd`, `Cl`,
  `Clf`, and `Clr` in run 1;
- [`AUTOCFD_DIAGNOSTICS_COMPOSITE_PROPOSAL.md`](AUTOCFD_DIAGNOSTICS_COMPOSITE_PROPOSAL.md):
  the review source for the active-candidate AutoCFD4/5 velocity-profile,
  continuous-Cp-cut native-segment reduction, and nine-component overall-score
  definitions, plus an explicitly inactive historical discrete-probe research
  record;
- `autocfd_cp_taps_nominal.csv`: inactive research coordinates for the 209
  unique nominal AutoCFD pressure taps;
- `autocfd_cp_panel_membership.csv`: their AutoCFD plot-panel ordering,
  including intentional reuse between panels; inactive research only;
- `autocfd_cp_tap_component_registry.csv`: the owner-review atlas connecting
  each nominal tap to one candidate named DrivAerML surface component and one
  per-case projection rule; its `component_assignment_*` values are anatomy
  audit evidence, not scoring support; visual owner sign-off is not an
  activation gate while the discrete probes remain excluded;
- `autocfd_velocity_lines_nominal.csv`: all 16 exact AutoCFD line endpoints and
  the fixed proposed 10 mm scoring and 1 mm validation counts;
- `autocfd_velocity_samples_10mm.csv`: all 3,756 explicit points on the fixed
  proposed scoring grid;
- `owner-published-splits.json`: the exact public train/validation/test lists;
- `split-index-candidates/`: FluidsBench-shaped test indexes derived without
  changing the owner-published order; and
- `native-source-pin.json`: immutable canonical boundary/volume and existing
  support-file identities for the 484 public cases (the named case-STL pin is
  an explicit remaining activation gate).

The active candidate must remain closed until the blockers in
`SCIENTIFIC_CONTRACT.md` and [`../ACTIVATION_CHECKLIST.md`](../ACTIVATION_CHECKLIST.md)
are resolved and the dataset owner approves one immutable scoring-support
release.
