def calculate_economics_from_results(results: dict, boiler_efficiency: float, fuel_price_rub_per_tut: float) -> dict:
    eta_turb = max(0.10, min(0.70, float(results.get("eta_brut", 30.0)) / 100.0))
    eta_total = max(0.05, eta_turb * boiler_efficiency)
    urut = 0.123 / eta_total * 1000.0
    fuel_cost_per_mwh = (urut / 1000.0) * fuel_price_rub_per_tut
    return {
        "eta_turbine": round(eta_turb, 4),
        "eta_total": round(eta_total, 4),
        "urut_g_per_kwh": round(urut, 3),
        "fuel_cost_rub_per_mwh": round(fuel_cost_per_mwh, 2),
    }
