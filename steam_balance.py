def calculate_station_steam_balance(results: dict) -> dict:
    regen = sum(float(results.get(key, 0.0)) for key in ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G_steam_d"))
    return {
        "regeneration_extractions_tph": round(regen, 3),
        "production_extraction_tph": round(float(results.get("Gprom", 0.0)), 3),
        "heating_upper_tph": round(float(results.get("G_vto", 0.0)), 3),
        "heating_lower_tph": round(float(results.get("G_nto", 0.0)), 3),
        "to_condenser_tph": round(float(results.get("G_cond", 0.0)), 3),
    }
