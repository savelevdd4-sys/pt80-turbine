from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from simulate_dynamic import run_simulation, build_results_dataframe
from dynamic_scenarios import list_scenarios, SCENARIO_LABELS

def _fallback_validate_critical_component_health(component_health, threshold=95.0):
    component_health = component_health or {}
    failed = []
    for key in ('cvd', 'csnd', 'ЦВД', 'ЦСНД'):
        if key in component_health and float(component_health.get(key, 100.0)) < float(threshold):
            failed.append(key)
    return {
        'valid': len(failed) == 0,
        'failed': failed,
        'threshold': float(threshold),
        'message': ('Критическое состояние: ' + ', '.join(failed)) if failed else ''
    }

try:
    from main import validate_critical_component_health as _validate_from_main
except Exception:
    _validate_from_main = None

def validate_critical_component_health(component_health, threshold=95.0):
    if _validate_from_main is not None:
        try:
            return _validate_from_main(component_health, threshold=threshold)
        except Exception:
            pass
    return _fallback_validate_critical_component_health(component_health, threshold=threshold)


@dataclass
class DynamicResult:
    scenario: str
    scenario_label: str
    table: pd.DataFrame
    summary: dict[str, Any]
    raw: dict[str, Any]


def list_dynamic_scenarios() -> list[dict[str, str]]:
    return [
        {"key": key, "label": SCENARIO_LABELS.get(key, key)}
        for key in list_scenarios()
    ]


def _sample_for_ui(df: pd.DataFrame, max_rows: int = 250) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    if len(df) <= max_rows:
        return df.copy()
    step = max(1, len(df) // max_rows)
    sampled = df.iloc[::step].copy()
    if sampled.index[-1] != df.index[-1]:
        sampled = pd.concat([sampled, df.iloc[[-1]].copy()], ignore_index=False)
    return sampled.reset_index(drop=True)


def _build_summary(df: pd.DataFrame, scenario: str) -> dict[str, Any]:
    if df is None or df.empty:
        return {
            "scenario": scenario,
            "scenario_label": SCENARIO_LABELS.get(scenario, scenario),
            "duration_s": 0.0,
            "initial": {},
            "final": {},
            "maxima": {},
        }

    first = df.iloc[0]
    last = df.iloc[-1]

    def _get(col: str, default: float = 0.0) -> float:
        return float(df[col].max()) if col in df.columns else float(default)

    summary = {
        "scenario": scenario,
        "scenario_label": SCENARIO_LABELS.get(scenario, scenario),
        "duration_s": float(df["t"].iloc[-1] - df["t"].iloc[0]) if "t" in df.columns else 0.0,
        "initial": {
            "power_mw": float(first.get("N_el_actual", 0.0)),
            "g0_tph": float(first.get("G0", 0.0)),
            "pk_kpa": float(first.get("P_k", 0.0)) * 1000.0,
            "omega_rads": float(first.get("omega", 0.0)),
        },
        "final": {
            "power_mw": float(last.get("N_el_actual", 0.0)),
            "g0_tph": float(last.get("G0", 0.0)),
            "pk_kpa": float(last.get("P_k", 0.0)) * 1000.0,
            "omega_rads": float(last.get("omega", 0.0)),
        },
        "maxima": {
            "max_power_mw": _get("N_el_actual"),
            "max_g0_tph": _get("G0"),
            "max_pk_kpa": _get("P_k") * 1000.0,
            "max_balance_error_tph": float(df["delta_balance"].abs().max()) if "delta_balance" in df.columns else 0.0,
        },
    }

    if "epd_margin_tph" in df.columns:
        summary["final"]["epd_margin_tph"] = float(last.get("epd_margin_tph", 0.0))
        summary["maxima"]["min_epd_margin_tph"] = float(df["epd_margin_tph"].min())
    if "epd_near" in df.columns:
        summary["maxima"]["epd_near_count"] = int(df["epd_near"].astype(bool).sum())
    if "epd_active" in df.columns:
        summary["maxima"]["epd_active_count"] = int(df["epd_active"].astype(bool).sum())

    return summary


def run_dynamic_simulation(
    scenario_name: str,
    t_end: float = 600.0,
    n_points: int = 1201,
    base_mode: dict[str, Any] | None = None,
    method: str = "Radau",
    max_step: float = 1.0,
) -> dict[str, Any]:
    base_mode = dict(base_mode or {})
    health_check = validate_critical_component_health(base_mode.get("component_health", {}))
    if not health_check.get("valid", True):
        empty = pd.DataFrame()
        return {
            "scenario": scenario_name,
            "scenario_label": SCENARIO_LABELS.get(scenario_name, scenario_name),
            "table": empty,
            "table_full": empty,
            "summary": {
                "scenario": scenario_name,
                "scenario_label": SCENARIO_LABELS.get(scenario_name, scenario_name),
                "duration_s": 0.0,
                "initial": {},
                "final": {},
                "maxima": {},
                "health_check": health_check,
            },
            "sol": None,
            "schedule": None,
            "dyn_params": None,
            "error": health_check.get("message", "Критическое состояние оборудования"),
        }
    sol, schedule, dyn_params = run_simulation(
        t_end=t_end,
        n_points=n_points,
        base_mode=base_mode,
        scenario_name=scenario_name,
        method=method,
        max_step=max_step,
    )
    df = build_results_dataframe(sol, schedule, dyn_params)
    summary = _build_summary(df, scenario_name)
    return {
        "scenario": scenario_name,
        "scenario_label": SCENARIO_LABELS.get(scenario_name, scenario_name),
        "table": _sample_for_ui(df),
        "table_full": df,
        "summary": summary,
        "sol": sol,
        "schedule": schedule,
        "dyn_params": dyn_params,
    }


def build_dynamic_table_for_ui(result: dict[str, Any]) -> pd.DataFrame:
    if not result:
        return pd.DataFrame()
    if isinstance(result.get("table"), pd.DataFrame):
        return result["table"]
    if isinstance(result.get("table_full"), pd.DataFrame):
        return _sample_for_ui(result["table_full"])
    return pd.DataFrame()
