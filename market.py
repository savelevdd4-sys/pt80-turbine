import math
import pandas as pd

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

def build_day_ahead_schedule(gprom: float, qtf: float, shema_tf: int, base_air_temp: float, boiler_eff: float, fuel_price: float, market_price: float, tech_limit_mw: float, fresh_steam_temp_c: float, component_health: dict | None = None) -> dict:
    rows = []
    component_health = component_health or {}
    for hour in range(24):
        t_air = base_air_temp + 5.0 * math.sin((hour - 6) / 24.0 * 2.0 * math.pi)
        # hours with higher heat demand: morning/evening
        qtf_h = qtf * (1.10 if 6 <= hour <= 9 or 18 <= hour <= 22 else 0.95)
        best = None
        for p in range(40, 101):
            try:
                calc = run_mode_calculation({"mode_id": f"H{hour:02d}-{p}", "Nz": float(p), "Gprom": gprom, "Qtf": qtf_h, "shema_tf": shema_tf, "component_health": component_health})
            except Exception:
                continue
            res = calc["results"]
            t_water = air_to_water_temp(t_air)
            pk_env = condenser_pressure_from_water_temp(t_water)
            nz_env = environmental_power_correction(_get_base_power(res), float(res["P_k"]) * 1000.0, pk_env)
            limits = evaluate_limits(nz_env, float(res["G0"]), pk_env, fresh_steam_temp_c, tech_limit_mw)
            eco = calculate_economics_from_results(res, boiler_eff, fuel_price)
            bid_mw = limits["available_power_mw"] - (5.0 if limits["has_limit"] else 2.0)
            bid_mw = max(0.0, round(bid_mw, 3))
            margin = market_price - eco["fuel_cost_rub_per_mwh"]
            profit = bid_mw * margin
            row = {
                "hour": hour,
                "t_air_c": round(t_air, 2),
                "t_water_c": round(t_water, 2),
                "qtf_gcal_h": round(qtf_h, 2),
                "requested_power_mw": float(p),
                "available_power_mw": round(limits["available_power_mw"], 3),
                "recommended_bid_mw": bid_mw,
                "fuel_cost_rub_per_mwh": eco["fuel_cost_rub_per_mwh"],
                "market_price_rub_per_mwh": market_price,
                "margin_rub_per_mwh": round(margin, 3),
                "profit_rub_per_h": round(profit, 3),
                "status": "Подавать" if margin > 0 else "Не подавать",
            }
            if best is None or row["profit_rub_per_h"] > best["profit_rub_per_h"]:
                best = row
        if best is None:
            best = {
                "hour": hour,
                "t_air_c": round(t_air, 2),
                "t_water_c": round(t_water, 2),
                "qtf_gcal_h": round(qtf_h, 2),
                "requested_power_mw": 0.0,
                "available_power_mw": 0.0,
                "recommended_bid_mw": 0.0,
                "fuel_cost_rub_per_mwh": float('nan'),
                "market_price_rub_per_mwh": market_price,
                "margin_rub_per_mwh": float('nan'),
                "profit_rub_per_h": 0.0,
                "status": "Недопустимый режим",
            }
        rows.append(best)
    table = pd.DataFrame(rows)
    return {"table": table}
