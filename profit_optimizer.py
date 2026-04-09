try:
    from services.calc_service import run_mode_calculation
except ImportError:
    from calc_service import run_mode_calculation
try:
    from models.environment_models import air_to_water_temp, condenser_pressure_from_water_temp, environmental_power_correction
except ImportError:
    from environment_models import air_to_water_temp, condenser_pressure_from_water_temp, environmental_power_correction
try:
    from models.turbine_limits import evaluate_limits
except ImportError:
    from turbine_limits import evaluate_limits
try:
    from models.economics import calculate_economics_from_results
except ImportError:
    from economics import calculate_economics_from_results


def _get_base_power(results: dict) -> float:
    return float(results.get("N_el_actual", results.get("N_el_calc", results.get("Nz", 0.0))))


def optimize_load_by_profit(gprom: float, qtf: float, shema_tf: int, t_air: float, boiler_eff: float, fuel_price: float, market_price: float, tech_limit_mw: float, fresh_steam_temp_c: float, component_health: dict | None = None) -> dict:
    points = []
    component_health = component_health or {}
    for pwr in range(40, 101):
        try:
            calc = run_mode_calculation({
                "mode_id": f"OPT-{pwr}",
                "Nz": float(pwr),
                "Gprom": gprom,
                "Qtf": qtf,
                "shema_tf": shema_tf,
                "component_health": component_health,
            })
        except Exception:
            continue
        res = calc["results"]
        t_water = air_to_water_temp(t_air)
        pk_env = condenser_pressure_from_water_temp(t_water)
        nz_env = environmental_power_correction(_get_base_power(res), float(res["P_k"]) * 1000.0, pk_env)
        limits = evaluate_limits(nz_env, float(res["G0"]), pk_env, fresh_steam_temp_c, tech_limit_mw)
        eco = calculate_economics_from_results(res, boiler_eff, fuel_price)
        available = limits["available_power_mw"]
        margin = market_price - eco["fuel_cost_rub_per_mwh"]
        profit = available * margin
        points.append({
            "requested_power_mw": float(pwr),
            "available_power_mw": round(available, 3),
            "gross_power_mw": round(float(res.get("N_el_calc", 0.0)), 3),
            "net_power_mw": round(float(res.get("N_el_net", 0.0)), 3),
            "steam_flow_tph": round(float(res.get("G0", 0.0)), 3),
            "fuel_cost_rub_per_mwh": eco["fuel_cost_rub_per_mwh"],
            "margin_rub_per_mwh": round(margin, 3),
            "profit_rub_per_h": round(profit, 3),
        })
    if not points:
        raise RuntimeError('Не найдено ни одной допустимой точки для оптимизации: режим упирается в ЕПД/эксплуатационные ограничения.')
    best = max(points, key=lambda x: x["profit_rub_per_h"])
    return {"optimal_power_mw": best["available_power_mw"], "curve": points, "best_point": best}
