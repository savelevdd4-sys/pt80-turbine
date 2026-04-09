from __future__ import annotations

import io
from contextlib import redirect_stdout
from typing import Any

import numpy as np

from config import etam, etag_nom, beta_vozvrat, t_vozvrat, tw1_nom, W_nom, tech_state_coeff_nom
from main import (
    calculate_initial_G0,
    calc_teplofik,
    normalize_component_health,
    apply_component_health_to_flows,
    apply_health_to_condenser,
    apply_health_to_teplofication,
    estimate_condenser_power_loss,
    calculate_mode,
)
from cvad import calc_pressures_cvd, calc_power_cvd
from csnd import calc_pressures_csnd_full, calc_power_csnd_full, calc_h_values_csnd
from cnd import calc_condenser
from regeneration import calc_regeneration_full


STATE_KEYS = [
    "G0",
    "P1", "P2", "P3", "P_prom",
    "P4", "P5", "P6", "P7", "P_vto", "P_nto", "P_k",
    "G1", "G2", "G3", "G4", "G5", "G6", "G7",
    "G_steam_d", "G_vto", "G_nto", "G_cond",
    "omega",
]

DEFAULT_PARAMS = {
    "T_G0": 2.0,
    "T_P1": 0.8,
    "T_P2": 0.8,
    "T_P3": 0.8,
    "T_P_prom": 1.0,
    "T_P4": 1.2,
    "T_P5": 1.2,
    "T_P6": 1.2,
    "T_P7": 1.2,
    "T_P_vto": 2.0,
    "T_P_nto": 2.0,
    "T_P_k": 8.0,
    "T_G1": 6.0,
    "T_G2": 6.0,
    "T_G3": 6.0,
    "T_G4": 6.0,
    "T_G5": 6.0,
    "T_G6": 6.0,
    "T_G7": 6.0,
    "T_G_steam_d": 5.0,
    "T_G_vto": 5.0,
    "T_G_nto": 5.0,
    "T_G_cond": 3.0,
    "omega_nom": 2.0 * np.pi * 50.0,
    "J_rotor": 25.0,
    "D_omega": 2.0,
    "k_balance": 0.5,
    "x_start": 0.98,
}


def _quiet_call(func, *args, **kwargs):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        return func(*args, **kwargs)


def pack_state(xd: dict[str, float]) -> np.ndarray:
    return np.array([float(xd[k]) for k in STATE_KEYS], dtype=float)


def unpack_state(x: np.ndarray | list[float] | tuple[float, ...]) -> dict[str, float]:
    x = np.asarray(x, dtype=float).reshape(-1)
    if x.size != len(STATE_KEYS):
        raise ValueError(f"Ожидалось {len(STATE_KEYS)} состояний, получено {x.size}")
    return {k: float(v) for k, v in zip(STATE_KEYS, x)}


def first_order(current: float, target: float, T: float) -> float:
    return (float(target) - float(current)) / max(float(T), 1e-9)


def _nonnegative(value: float) -> float:
    return max(0.0, float(value))


def algebraic_outputs(
    x: np.ndarray | list[float] | tuple[float, ...],
    u: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    p = dict(DEFAULT_PARAMS)
    if params:
        p.update(params)

    s = unpack_state(x)

    Nz = float(u["Nz"])
    Gprom = float(u["Gprom"])
    Qtf = float(u["Qtf"])
    shema_tf = int(u["shema_tf"])
    W_cw = float(u.get("W_cw", W_nom))
    tw1 = float(u.get("tw1", tw1_nom))
    tech_state_coeff = float(u.get("tech_state_coeff", tech_state_coeff_nom))
    component_health = normalize_component_health(u.get("component_health", {}))
    N_e = float(u.get("N_e", Nz))

    G0_ref = float(_quiet_call(calculate_initial_G0, Nz, Gprom, Qtf, shema_tf))

    cvd_pressures_ref = _quiet_call(calc_pressures_cvd, s["G0"], s["G1"], s["G2"], s["G3"])
    N_cvd_raw, h_prom, cvd_enthalpies = _quiet_call(
        calc_power_cvd,
        s["G0"], s["G1"], s["G2"], s["G3"], cvd_pressures_ref,
    )

    csnd_pressures_ref = _quiet_call(
        calc_pressures_csnd_full,
        cvd_pressures_ref["G_cvd_out"],
        Gprom,
        s["G4"], s["G5"], s["G6"], s["G7"],
        s["G_vto"], s["G_nto"],
        cvd_pressures_ref["P_prom"],
    )

    csnd_enthalpies_pre = _quiet_call(
        calc_h_values_csnd,
        csnd_pressures_ref,
        h_prom,
        x_start=p["x_start"],
    )

    if Qtf > 1e-9:
        tf_results = _quiet_call(calc_teplofik, Qtf, shema_tf, csnd_pressures_ref["P_vto"], csnd_pressures_ref["P_nto"])
        tf_results = apply_health_to_teplofication(tf_results, component_health, shema_tf)
        G_vto_ref = _nonnegative(tf_results.get("G_vto", 0.0))
        G_nto_ref = _nonnegative(tf_results.get("G_nto", 0.0))
        dN_tf = float(tf_results.get("dN_tf", 0.0))
    else:
        G_vto_ref = 0.0
        G_nto_ref = 0.0
        dN_tf = 0.0

    W_cw_effective = W_cw * component_health["condenser"] / 100.0
    cond_results = _quiet_call(
        calc_condenser,
        _nonnegative(s["G_cond"]),
        csnd_enthalpies_pre["h_k"],
        W_cw_effective,
        tw1,
    )
    P_k_ref = float(apply_health_to_condenser(cond_results["P_k"], component_health))

    csnd_pressures_actual = dict(csnd_pressures_ref)
    csnd_pressures_actual["P_k"] = float(s["P_k"])
    csnd_enthalpies = _quiet_call(calc_h_values_csnd, csnd_pressures_actual, h_prom, x_start=p["x_start"])

    G_ok = max(
        50.0,
        s["G0"] - s["G1"] - s["G2"] - s["G3"] - s["G4"] - s["G5"] - s["G6"] - s["G7"] - Gprom - s["G_vto"] - s["G_nto"],
    )
    t_k = float(cond_results["tsat"]) + 3.0
    G_return = Gprom * beta_vozvrat

    reg_results = _quiet_call(
        calc_regeneration_full,
        cvd_pressures_ref,
        csnd_pressures_actual,
        csnd_enthalpies,
        G_ok,
        t_k,
        G_return,
        t_vozvrat,
    )

    scaled_flows = apply_component_health_to_flows(
        component_health,
        {
            "G1": reg_results.get("G1", s["G1"]),
            "G2": reg_results.get("G2", s["G2"]),
            "G3": reg_results.get("G3", s["G3"]),
            "G4": reg_results.get("G4", s["G4"]),
            "G5": reg_results.get("G5", s["G5"]),
            "G6": reg_results.get("G6", s["G6"]),
            "G7": reg_results.get("G7", s["G7"]),
            "G_steam_d": reg_results.get("G_steam_d", s["G_steam_d"]),
        },
    )

    N_csnd_raw = _quiet_call(
        calc_power_csnd_full,
        h_prom,
        csnd_enthalpies["h4"], csnd_enthalpies["h5"], csnd_enthalpies["h6"], csnd_enthalpies["h7"],
        csnd_enthalpies["h_vto"], csnd_enthalpies["h_nto"], csnd_enthalpies["h_k"],
        cvd_pressures_ref["G_cvd_out"],
        Gprom,
        s["G4"], s["G5"], s["G6"], s["G7"],
        s["G_vto"], s["G_nto"],
    )

    N_cvd = float(N_cvd_raw) * component_health["cvd"] / 100.0
    N_csnd = float(N_csnd_raw) * component_health["csnd"] / 100.0
    generator_factor = component_health["generator"] / 100.0
    N_el_gross = (N_cvd + N_csnd) * etam * etag_nom * tech_state_coeff * generator_factor
    dN_cond = float(estimate_condenser_power_loss(s["G_cond"], s["P_k"]))
    N_el_actual = max(0.0, N_el_gross - dN_cond)

    G_otbory = s["G1"] + s["G2"] + s["G3"] + s["G4"] + s["G5"] + s["G6"] + s["G7"] + s["G_steam_d"] + Gprom + s["G_vto"] + s["G_nto"]
    delta_balance = s["G0"] - (G_otbory + s["G_cond"])
    G_cond_ref = _nonnegative(float(csnd_pressures_ref.get("G_k", 0.0)) + p["k_balance"] * delta_balance)

    refs = {
        "G0_ref": G0_ref,
        "P1_ref": float(cvd_pressures_ref["P1"]),
        "P2_ref": float(cvd_pressures_ref["P2"]),
        "P3_ref": float(cvd_pressures_ref["P3"]),
        "P_prom_ref": float(cvd_pressures_ref["P_prom"]),
        "P4_ref": float(csnd_pressures_ref["P4"]),
        "P5_ref": float(csnd_pressures_ref["P5"]),
        "P6_ref": float(csnd_pressures_ref["P6"]),
        "P7_ref": float(csnd_pressures_ref["P7"]),
        "P_vto_ref": float(csnd_pressures_ref["P_vto"]),
        "P_nto_ref": float(csnd_pressures_ref["P_nto"]),
        "P_k_ref": P_k_ref,
        "G1_ref": _nonnegative(scaled_flows["G1"]),
        "G2_ref": _nonnegative(scaled_flows["G2"]),
        "G3_ref": _nonnegative(scaled_flows["G3"]),
        "G4_ref": _nonnegative(scaled_flows["G4"]),
        "G5_ref": _nonnegative(scaled_flows["G5"]),
        "G6_ref": _nonnegative(scaled_flows["G6"]),
        "G7_ref": _nonnegative(scaled_flows["G7"]),
        "G_steam_d_ref": _nonnegative(scaled_flows["G_steam_d"]),
        "G_vto_ref": G_vto_ref,
        "G_nto_ref": G_nto_ref,
        "G_cond_ref": G_cond_ref,
    }

    return {
        "refs": refs,
        "cvd_pressures_ref": cvd_pressures_ref,
        "csnd_pressures_ref": csnd_pressures_ref,
        "csnd_pressures_actual": csnd_pressures_actual,
        "cvd_enthalpies": cvd_enthalpies,
        "csnd_enthalpies": csnd_enthalpies,
        "cond_results": cond_results,
        "reg_results": reg_results,
        "N_cvd": N_cvd,
        "N_csnd": N_csnd,
        "N_el_gross": N_el_gross,
        "N_el_actual": N_el_actual,
        "dN_cond": dN_cond,
        "dN_tf": dN_tf,
        "delta_balance": delta_balance,
        "N_e": N_e,
        "component_health": component_health,
        "W_cw_effective": W_cw_effective,
        "Gprom": Gprom,
        "Qtf": Qtf,
        "shema_tf": shema_tf,
        "Nz": Nz,
    }


def rhs(
    t: float,
    x: np.ndarray | list[float] | tuple[float, ...],
    u: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> np.ndarray:
    p = dict(DEFAULT_PARAMS)
    if params:
        p.update(params)

    s = unpack_state(x)
    alg = algebraic_outputs(x, u, p)
    refs = alg["refs"]
    dx = {k: 0.0 for k in STATE_KEYS}

    dx["G0"] = first_order(s["G0"], refs["G0_ref"], p["T_G0"])
    dx["G1"] = first_order(s["G1"], refs["G1_ref"], p["T_G1"])
    dx["G2"] = first_order(s["G2"], refs["G2_ref"], p["T_G2"])
    dx["G3"] = first_order(s["G3"], refs["G3_ref"], p["T_G3"])
    dx["G4"] = first_order(s["G4"], refs["G4_ref"], p["T_G4"])
    dx["G5"] = first_order(s["G5"], refs["G5_ref"], p["T_G5"])
    dx["G6"] = first_order(s["G6"], refs["G6_ref"], p["T_G6"])
    dx["G7"] = first_order(s["G7"], refs["G7_ref"], p["T_G7"])
    dx["G_steam_d"] = first_order(s["G_steam_d"], refs["G_steam_d_ref"], p["T_G_steam_d"])
    dx["G_vto"] = first_order(s["G_vto"], refs["G_vto_ref"], p["T_G_vto"])
    dx["G_nto"] = first_order(s["G_nto"], refs["G_nto_ref"], p["T_G_nto"])
    dx["G_cond"] = first_order(s["G_cond"], refs["G_cond_ref"], p["T_G_cond"])

    dx["P1"] = first_order(s["P1"], refs["P1_ref"], p["T_P1"])
    dx["P2"] = first_order(s["P2"], refs["P2_ref"], p["T_P2"])
    dx["P3"] = first_order(s["P3"], refs["P3_ref"], p["T_P3"])
    dx["P_prom"] = first_order(s["P_prom"], refs["P_prom_ref"], p["T_P_prom"])
    dx["P4"] = first_order(s["P4"], refs["P4_ref"], p["T_P4"])
    dx["P5"] = first_order(s["P5"], refs["P5_ref"], p["T_P5"])
    dx["P6"] = first_order(s["P6"], refs["P6_ref"], p["T_P6"])
    dx["P7"] = first_order(s["P7"], refs["P7_ref"], p["T_P7"])
    dx["P_vto"] = first_order(s["P_vto"], refs["P_vto_ref"], p["T_P_vto"])
    dx["P_nto"] = first_order(s["P_nto"], refs["P_nto_ref"], p["T_P_nto"])
    dx["P_k"] = first_order(s["P_k"], refs["P_k_ref"], p["T_P_k"])

    dx["omega"] = (
        alg["N_el_gross"]
        - alg["N_e"]
        - p["D_omega"] * (s["omega"] - p["omega_nom"])
    ) / max(p["J_rotor"], 1e-9)

    return pack_state(dx)


def build_initial_state(mode_data: dict[str, Any], params: dict[str, Any] | None = None) -> np.ndarray:
    p = dict(DEFAULT_PARAMS)
    if params:
        p.update(params)

    mode = dict(mode_data)
    mode.setdefault("mode_id", "DYN-INIT")
    mode.setdefault("W", mode.get("W_cw", W_nom))
    mode.setdefault("tw1", mode.get("tw1", tw1_nom))
    mode.setdefault("tech_state_coeff", mode.get("tech_state_coeff", tech_state_coeff_nom))
    mode.setdefault("component_health", mode.get("component_health", {}))

    results = _quiet_call(calculate_mode, mode)
    x0 = {
        "G0": float(results["G0"]),
        "P1": float(results["P1"]),
        "P2": float(results["P2"]),
        "P3": float(results["P3"]),
        "P_prom": float(results["P_prom"]),
        "P4": float(results["P4"]),
        "P5": float(results["P5"]),
        "P6": float(results["P6"]),
        "P7": float(results["P7"]),
        "P_vto": float(results["P_vto"]),
        "P_nto": float(results["P_nto"]),
        "P_k": float(results["P_k"]),
        "G1": float(results["G1"]),
        "G2": float(results["G2"]),
        "G3": float(results["G3"]),
        "G4": float(results["G4"]),
        "G5": float(results["G5"]),
        "G6": float(results["G6"]),
        "G7": float(results["G7"]),
        "G_steam_d": float(results["G_steam_d"]),
        "G_vto": float(results["G_vto"]),
        "G_nto": float(results["G_nto"]),
        "G_cond": float(results["G_cond"]),
        "omega": float(p["omega_nom"]),
    }
    return pack_state(x0)
