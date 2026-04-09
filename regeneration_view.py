def build_regeneration_view(results: dict) -> dict:
    rows = [
        {"group": "ПВД", "element": "ПВД-7", "flow_tph": float(results.get("G1", 0.0))},
        {"group": "ПВД", "element": "ПВД-6", "flow_tph": float(results.get("G2", 0.0))},
        {"group": "ПВД", "element": "ПВД-5", "flow_tph": float(results.get("G3", 0.0))},
        {"group": "ПНД", "element": "ПНД-4", "flow_tph": float(results.get("G4", 0.0))},
        {"group": "ПНД", "element": "ПНД-3", "flow_tph": float(results.get("G5", 0.0))},
        {"group": "ПНД", "element": "ПНД-2", "flow_tph": float(results.get("G6", 0.0))},
        {"group": "ПНД", "element": "ПНД-1", "flow_tph": float(results.get("G7", 0.0))},
        {"group": "ДА", "element": "Пар на деаэратор", "flow_tph": float(results.get("G_steam_d", 0.0))},
    ]

    summary = {
        "t_ok_c": float(results.get("t_ok", 0.0)),
        "t_pv_c": float(results.get("t_pv", 0.0)),
        "total_regen_flow_tph": round(sum(row["flow_tph"] for row in rows), 3),
    }
    return {"rows": rows, "summary": summary}
