# AirfRANS Profile Extraction Example

This directory contains the reference extraction script for producing FluidsBench-compliant 1D boundary layer velocity profiles from the native 3D unstructured AirfRANS dataset.

## Dependencies
This script is strictly validated against the environment defined in the `benchmark-specs/airfrans/velocity-profiles-v1.json` contract:
* `airfrans == 0.1.5.1`
* `pyvista == 0.48.4`
* `vtk == 9.6.2`

## Usage
To regenerate the `example_extraction.json` fixture using the official ground truth dataset:

```bash
python3 extract.py --dataset-root /path/to/AirfRANS/Dataset
```

## ML Prediction Workflow
Surrogate model researchers are not required to format their outputs into `.vtu` files on disk to generate submission payloads. The `extract.py` script contains commented instructions to hot-swap PyTorch or NumPy predictions directly into the `airfrans.Simulation` velocity and pressure arrays in-memory prior to calling the `boundary_layer` routine.
