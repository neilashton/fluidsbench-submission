import os
import json
import hashlib

def hash_file(filepath):
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()

def calculate_scores(metrics):
    # Cap qualities at 0 and 1, convert to %
    cd = max(0.0, min(1.0, metrics.get("cd_r2", 0))) * 100
    cl = max(0.0, min(1.0, metrics.get("cl_r2", 0))) * 100
    vp = max(0.0, min(1.0, metrics.get("velocity_profile_r2", 0))) * 100

    def bound_err(val, cap):
        return max(0.0, 100 * (1.0 - (val / cap)))

    s_sp = bound_err(metrics.get("surface_pressure_rel_l2", 0), 15.0)
    s_sws = bound_err(metrics.get("surface_wall_shear_rel_l2", 0), 20.0)
    s_fdv = bound_err(metrics.get("flow_domain_velocity_rel_l2", 0), 12.0)
    s_fdp = bound_err(metrics.get("flow_domain_pressure_rel_l2", 0), 15.0)

    # Updated with your exact weights
    field_score = (0.16 * s_sp + 0.18 * s_sws + 0.22 * s_fdv + 0.11 * s_fdp) / 0.67
    force_score = (0.12 * cd + 0.10 * cl) / 0.22
    diagnostic_score = vp
    overall = (0.16 * s_sp) + (0.18 * s_sws) + (0.22 * s_fdv) + (0.11 * s_fdp) + (0.12 * cd) + (0.10 * cl) + (0.11 * vp)

    return field_score, force_score, diagnostic_score, overall

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    splits_dir = os.path.join(base_dir, "benchmark-specs", "airfrans", "splits")
    submissions_dir = os.path.join(base_dir, "submissions", "airfrans")

    subs_map = {
        "airfrans-pointnet-full": "full",
        "dummy-airfrans-airfoiloperator-v1": "full",
        "airfrans-graph-u-net-full": "scarce",
        "airfrans-graphsage-full": "reynolds_extrapolation",
        "airfrans-mlp-full": "aoa_extrapolation"
    }

    stations = ["upper_x_0_25c", "upper_x_0_50c", "upper_x_0_75c", "upper_x_0_95c"]

    for sub_folder, split_id in subs_map.items():
        sub_path = os.path.join(submissions_dir, sub_folder)
        if not os.path.exists(sub_path):
            continue
        
        # Read splits & submission metadata
        split_file = os.path.join(splits_dir, f"{split_id}.json")
        split_sha256 = hash_file(split_file)
        with open(split_file, 'r') as f:
            cases = json.load(f)["case_ids"]
            
        sub_file = os.path.join(sub_path, "submission.json")
        with open(sub_file, 'r') as f:
            sub = json.load(f)
            
        case_set_id = sub.get("case_set_id", "standard")
        
        # Generate formatted Profiles
        prof_dir = os.path.join(sub_path, "profiles")
        os.makedirs(prof_dir, exist_ok=True)
        
        # Clean old chunks
        for f in os.listdir(prof_dir):
            os.remove(os.path.join(prof_dir, f))
            
        chunk_file = os.path.join(prof_dir, "chunk-000.json")
        chunk_data = {
            "schema_version": "1.0",
            "cases": []
        }
        
        for case in cases:
            case_obj = {
                "case_id": case,
                "series": []
            }
            for st in stations:
                case_obj["series"].append({
                    "panel_id": "velocity_profiles",
                    "station_id": st,
                    "quantity_id": "velocity_ratio",
                    "coordinate": [0.0, 0.05, 0.1],
                    "prediction": [1.0, 1.0, 1.0]
                })
            chunk_data["cases"].append(case_obj)
            
        with open(chunk_file, 'w') as f:
            json.dump(chunk_data, f, indent=2)
            
        index_file = os.path.join(prof_dir, "index.json")
        index_data = {
            "schema_version": "1.0",
            "submission_id": sub_folder,
            "dataset_id": "airfrans",
            "split_id": split_id,
            "case_set_id": case_set_id,
            "case_count": len(cases),
            "chunks": [
                {
                    "file": "chunk-000.json",
                    "case_ids": cases,
                    "sha256": hash_file(chunk_file)
                }
            ]
        }
        with open(index_file, 'w') as f:
            json.dump(index_data, f, indent=2)

        # update evaluation-evidence.json
        ev_file = os.path.join(sub_path, "evaluation-evidence.json")
        with open(ev_file, 'r') as f:
            ev = json.load(f)
            
        metrics = ev["metric_values"]
        metrics.pop("cp_cut_r2", None)
        
        f_score, force_score, diag_score, overall = calculate_scores(metrics)
        metrics["field_score"] = f_score
        metrics["force_score"] = force_score
        metrics["diagnostic_score"] = diag_score
        metrics["overall_score"] = overall
        
        ev["profile_index_sha256"] = hash_file(index_file)
        with open(ev_file, 'w') as f:
            json.dump(ev, f, indent=2)

        # update submission.json
        sub["split_sha256"] = split_sha256
        sub["metric_values"] = metrics
        sub["evaluation"]["evidence_sha256"] = hash_file(ev_file)
        sub["profile_data"]["case_count"] = len(cases)
        sub["profile_data"]["index_file"] = "profiles/index.json"
        
        with open(sub_file, 'w') as f:
            json.dump(sub, f, indent=2)
            
        print(f"Successfully formatted prototype for: {sub_folder}")

if __name__ == "__main__":
    main()