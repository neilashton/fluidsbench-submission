# DrivAerML scientific-contract proposal

This directory is a non-activating proposal for dataset-owner and FluidsBench
review. It deliberately does not modify the current prototype
`../submission-spec.json`, its dummy case IDs, or historical submissions.

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

Files:

- [`SCIENTIFIC_CONTRACT.md`](SCIENTIFIC_CONTRACT.md): review rationale and the
  proposed human-readable contract;
- [`contract-proposal.json`](contract-proposal.json): the same decisions in a
  machine-readable form;
- `owner-published-splits.json`: the exact public train/validation/test lists;
- `split-index-candidates/`: FluidsBench-shaped test indexes derived without
  changing the owner-published order; and
- `native-source-pin.json`: immutable file identities for the 484 public cases.

The proposal must remain closed until the blockers in
`SCIENTIFIC_CONTRACT.md` are resolved and the dataset owner approves one
immutable scoring-support release.
