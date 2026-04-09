from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from config import W_nom, tw1_nom, tech_state_coeff_nom

Schedule = Callable[[float], dict[str, Any]]
Modifier = Callable[[float, dict[str, Any]], None]

DEFAULT_BASE_MODE = {
    "mode_id": "DYN-BASE",
    "Nz": 80.0,
    "Gprom": 51.3,
    "Qtf": 78.9,
    "shema_tf": 2,
    "W_cw": float(W_nom),
    "tw1": float(tw1_nom),
    "tech_state_coeff": float(tech_state_coeff_nom),
    "component_health": {
        "cvd": 100.0,
        "csnd": 100.0,
        "condenser": 100.0,
        "generator": 100.0,
        "pvd7": 100.0,
        "pvd6": 100.0,
        "pvd5": 100.0,
        "pnd4": 100.0,
        "pnd3": 100.0,
        "pnd2": 100.0,
        "pnd1": 100.0,
        "deaerator": 100.0,
        "psg1": 100.0,
        "psg2": 100.0,
    },
    "N_e": 80.0,
}

SCENARIO_LABELS = {
    "стационарный": "Стационарный режим",
    "нагрузка_ступень": "Ступенчатое изменение электрической нагрузки",
    "теплофикация_ступень": "Ступенчатое изменение теплофикационной нагрузки",
    "производственный_отбор_ступень": "Ступенчатое изменение производственного отбора",
    "температура_охлаждающей_воды_ступень": "Ступенчатое изменение температуры охлаждающей воды",
    "снижение_расхода_охлаждающей_воды": "Ступенчатое снижение расхода охлаждающей воды",
    "деградация_конденсатора": "Ухудшение состояния конденсатора",
    "комбинированный_демо": "Комбинированный демонстрационный режим",
    "летний_пик": "Летний пиковый режим",
}

SCENARIO_ALIASES = {
    "steady": "стационарный",
    "load_step": "нагрузка_ступень",
    "heat_step": "теплофикация_ступень",
    "production_step": "производственный_отбор_ступень",
    "cooling_temp_step": "температура_охлаждающей_воды_ступень",
    "cooling_flow_drop": "снижение_расхода_охлаждающей_воды",
    "condenser_degradation": "деградация_конденсатора",
    "combined_demo": "комбинированный_демо",
    "summer_peak": "летний_пик",
}


def normalize_scenario_name(name: str) -> str:
    if not name:
        return "стационарный"
    name = str(name).strip()
    if name in SCENARIO_LABELS:
        return name
    return SCENARIO_ALIASES.get(name, name)


def make_base_mode(**overrides: Any) -> dict[str, Any]:
    base = deepcopy(DEFAULT_BASE_MODE)
    for key, value in overrides.items():
        if key == "component_health" and isinstance(value, dict):
            base["component_health"].update(value)
        else:
            base[key] = value
    return base


def constant_schedule(base_mode: dict[str, Any]) -> Schedule:
    base = deepcopy(base_mode)
    base.setdefault("N_e", base["Nz"])
    return lambda t: deepcopy(base)


def compose_schedule(base_mode: dict[str, Any], *modifiers: Modifier) -> Schedule:
    base = deepcopy(base_mode)
    base.setdefault("N_e", base["Nz"])

    def schedule(t: float) -> dict[str, Any]:
        u = deepcopy(base)
        for modifier in modifiers:
            modifier(float(t), u)
        return u

    return schedule


def step_change(t_start: float, **updates: Any) -> Modifier:
    def modifier(t: float, u: dict[str, Any]) -> None:
        if t < t_start:
            return
        for key, value in updates.items():
            if key == "component_health" and isinstance(value, dict):
                u.setdefault("component_health", {})
                u["component_health"].update(value)
            else:
                u[key] = value
    return modifier


def step_load(t_start: float, new_load_mw: float, follow_setpoint: bool = True) -> Modifier:
    def modifier(t: float, u: dict[str, Any]) -> None:
        if t >= t_start:
            u["N_e"] = new_load_mw
            if follow_setpoint:
                u["Nz"] = new_load_mw
    return modifier


def step_heat_load(t_start: float, new_qtf_gcal_h: float) -> Modifier:
    return step_change(t_start, Qtf=new_qtf_gcal_h)


def step_production_extraction(t_start: float, new_gprom_tph: float) -> Modifier:
    return step_change(t_start, Gprom=new_gprom_tph)


def step_cooling_water_temp(t_start: float, new_tw1_c: float) -> Modifier:
    return step_change(t_start, tw1=new_tw1_c)


def step_cooling_water_flow(t_start: float, new_w_cw_m3_h: float) -> Modifier:
    return step_change(t_start, W_cw=new_w_cw_m3_h)


def step_component_health(t_start: float, component: str, new_health_percent: float) -> Modifier:
    return step_change(t_start, component_health={component: new_health_percent})


def get_scenario_registry(base_mode: dict[str, Any] | None = None) -> dict[str, Schedule]:
    base = make_base_mode(**(base_mode or {})) if isinstance(base_mode, dict) else make_base_mode()

    registry = {
        "стационарный": constant_schedule(base),
        "нагрузка_ступень": compose_schedule(base, step_load(100.0, 90.0, follow_setpoint=True)),
        "теплофикация_ступень": compose_schedule(base, step_heat_load(100.0, 88.9)),
        "производственный_отбор_ступень": compose_schedule(base, step_production_extraction(100.0, 70.0)),
        "температура_охлаждающей_воды_ступень": compose_schedule(base, step_cooling_water_temp(100.0, 25.0)),
        "снижение_расхода_охлаждающей_воды": compose_schedule(base, step_cooling_water_flow(100.0, 6500.0)),
        "деградация_конденсатора": compose_schedule(base, step_component_health(100.0, "condenser", 90.0)),
        "комбинированный_демо": compose_schedule(
            base,
            step_load(100.0, 90.0, follow_setpoint=True),
            step_heat_load(200.0, 88.9),
            step_cooling_water_temp(300.0, 25.0),
            step_component_health(400.0, "condenser", 90.0),
        ),
        "летний_пик": compose_schedule(
            base,
            step_load(60.0, 95.0, follow_setpoint=True),
            step_heat_load(120.0, 95.0),
            step_cooling_water_temp(180.0, 28.0),
            step_cooling_water_flow(240.0, 7000.0),
        ),
    }
    return registry


def list_scenarios(base_mode: dict[str, Any] | None = None) -> list[str]:
    return list(get_scenario_registry(base_mode).keys())


def get_schedule(name: str, base_mode: dict[str, Any] | None = None) -> Schedule:
    scenario_key = normalize_scenario_name(name)
    registry = get_scenario_registry(base_mode)
    if scenario_key not in registry:
        raise KeyError(
            f"Неизвестный сценарий: {name}. Доступные: {', '.join(registry.keys())}"
        )
    return registry[scenario_key]
