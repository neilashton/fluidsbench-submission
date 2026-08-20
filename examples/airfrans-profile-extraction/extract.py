import argparse
import json
import hashlib
import numpy as np
import pyvista as pv
import vtk
import airfrans as af
from pathlib import Path

def get_file_hash(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()

def main():
    parser = argparse.ArgumentParser(description="Regenerate the AirfRANS ground-truth extraction example.")
    parser.add_argument("--dataset-root", type=str, required=True, help="Path to the main AirfRANS Dataset folder.")
    args = parser.parse_args()

    CASE_NAME = "airFoil2D_SST_31.812_1.334_0.371_3.287_0.0_19.548"
    dataset_dir = Path(args.dataset_root)
    case_dir = dataset_dir / CASE_NAME
    
    repo_root = Path(__file__).resolve().parents[2]
    spec_path = repo_root / "benchmark-specs" / "airfrans" / "velocity-profiles-v1.json"
    out_dir = repo_root / "examples" / "airfrans-profile-extraction"
    
    with open(spec_path, 'r') as f:
        spec = json.load(f)
        
    ext_rules = spec["extraction"]
    stations = spec["stations"]
    quantities = spec["quantities"]
    expected_len = ext_rules["sample_count"]
    panel_id = spec["metric_binding"]["panel_id"]

    provenance = {
        "versions": {
            "airfrans": af.__version__,
            "pyvista": pv.__version__,
            "vtk": vtk.vtkVersion.GetVTKVersion(),
            "numpy": np.__version__
        },
        "input_hashes": {}
    }
    
    vtu_file = case_dir / f"{CASE_NAME}_internal.vtu"
    vtp_file = case_dir / f"{CASE_NAME}_aerofoil.vtp"
    
    if not vtu_file.exists() or not vtp_file.exists():
        raise FileNotFoundError(f"Missing VTU/VTP files in {case_dir}")

    provenance["input_hashes"]["internal_vtu"] = get_file_hash(vtu_file)
    provenance["input_hashes"]["aerofoil_vtp"] = get_file_hash(vtp_file)

    s_coord = np.linspace(0.0, ext_rules["line_length_m"], expected_len).tolist()

    sim_gt = af.Simulation(root=str(dataset_dir), name=CASE_NAME)
    gt_call_args = ext_rules["ground_truth_call_arguments"]
    
    series_output = []
    for st in stations:
        x_c = st["x_over_c"]
        station_id = st["id"]
        
        # --- SWAP HERE YOUR ML PREDICTIONS !! ---
        # To evaluate a surrogate model without writing unstructured .vtu files back to disk, 
        # load your predictions (e.g., from a .pkl, .npz, or PyTorch tensor) and overwrite 
        # the simulation's arrays in memory before extraction. For example:
        #
        # predicted_fields = np.load("my_predictions.npy")
        # sim_pred.velocity = predicted_fields[:, :2] 
        # sim_pred.pressure = predicted_fields[:, 2]
        # ----------------------------------------------------

        _, ux, uy, _, _ = sim_gt.boundary_layer(x=x_c, **gt_call_args)
        
        assert len(ux) == expected_len, f"Sample count mismatch at {station_id}"
        assert np.isfinite(ux).all() and np.isfinite(uy).all(), f"NaN values at {station_id}"
        
        for qty in quantities:
            data_array = ux if qty["routine_output_index"] == 1 else uy
            series_output.append({
                "panel_id": panel_id,
                "station_id": station_id,
                "quantity_id": qty["id"],
                "coordinate": s_coord,
                "prediction": data_array.tolist()
            })

    output_json = {
        "schema_version": "1.0",
        "provenance": provenance,
        "cases": [
            {
                "case_id": CASE_NAME,
                "series": series_output
            }
        ]
    }
    
    out_file = out_dir / "example_extraction.json"
    with open(out_file, 'w') as f:
        json.dump(output_json, f, indent=2)

if __name__ == "__main__":
    main()