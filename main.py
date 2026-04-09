# main.py
"""
Основной модуль стационарного расчёта турбины ПТ-80/100-130/13.

Что реализовано в этой версии:
- расчёт ЦВД / ЦСНД / конденсатора / регенерации / ПСГ;
- учёт технического состояния оборудования;
- блокировка расчёта при критическом состоянии ЦВД или ЦСНД (<95%);
- жёсткая остановка при выходе за Т-огибающую / ЕПД;
- дополнительная ПТ-валидация по мнимой мощности и Qтф(Qпр), если задан Qprom;
- Gprom остаётся массовым производственным отбором (т/ч) и участвует в паровом балансе;
- Qprom используется отдельно, только как тепловая нагрузка производственного отбора
  для ПТ-режимной валидации.
"""

from __future__ import annotations

import math
from typing import Dict, Any, List, Tuple, Optional

import numpy as np

try:
    from models.psg import calc_psg
except ImportError:
    from psg import calc_psg

from config import *
from steam_properties import ts, h_steam, h_water, h_steam_sat, h_water_temp
from cvad import calc_pressures_cvd, calc_power_cvd
from csnd import calc_pressures_csnd_full, calc_power_csnd_full, calc_h_values_csnd
from cnd import calc_condenser
from regeneration import calc_regeneration_full


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def print_separator(title: str = "") -> None:
    print("\n" + "=" * 80)
    if title:
        print(f"{title:^80}")
        print("=" * 80)


def kgs_to_th(kg_s: float) -> float:
    return float(kg_s) * 3600.0 / 1000.0


def th_to_kgs(t_h: float) -> float:
    return float(t_h) * 1000.0 / 3600.0


# ============================================================================
# ОПЦИИ И СОСТОЯНИЕ ОБОРУДОВАНИЯ
# ============================================================================

def normalize_component_health(component_health: Any) -> Dict[str, float]:
    default_map = {
        'cvd': 100.0,
        'csnd': 100.0,
        'condenser': 100.0,
        'generator': 100.0,
        'pvd7': 100.0,
        'pvd6': 100.0,
        'pvd5': 100.0,
        'pnd4': 100.0,
        'pnd3': 100.0,
        'pnd2': 100.0,
        'pnd1': 100.0,
        'deaerator': 100.0,
        'psg1': 100.0,
        'psg2': 100.0,
    }
    if not isinstance(component_health, dict):
        component_health = {}

    result: Dict[str, float] = {}
    for key, default in default_map.items():
        try:
            value = float(component_health.get(key, default))
        except Exception:
            value = default
        result[key] = float(np.clip(value, 0.0, 100.0))
    return result


def validate_critical_component_health(component_health: Dict[str, float]) -> Dict[str, Any]:
    health = normalize_component_health(component_health)
    issues: List[str] = []

    cvd = float(health.get('cvd', 100.0))
    csnd = float(health.get('csnd', 100.0))

    if cvd < 95.0:
        issues.append(f"ЦВД={cvd:.1f}% < 95%")
    if csnd < 95.0:
        issues.append(f"ЦСНД={csnd:.1f}% < 95%")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "message": "" if not issues else "Критическое состояние оборудования: " + "; ".join(issues),
    }


def hfactor(component_health: Dict[str, float], key: str) -> float:
    return normalize_component_health(component_health).get(key, 100.0) / 100.0


def apply_component_health_to_flows(component_health: Dict[str, float], values: Dict[str, float]) -> Dict[str, float]:
    health = normalize_component_health(component_health)
    scaled = dict(values)
    flow_keys = {
        'G1': 'pvd7',
        'G2': 'pvd6',
        'G3': 'pvd5',
        'G4': 'pnd4',
        'G5': 'pnd3',
        'G6': 'pnd2',
        'G7': 'pnd1',
        'G_steam_d': 'deaerator',
    }
    for flow_key, comp_key in flow_keys.items():
        if flow_key in scaled:
            scaled[flow_key] = float(scaled[flow_key]) * health[comp_key] / 100.0
    return scaled


def apply_health_to_condenser(pk_value: float, component_health: Dict[str, float]) -> float:
    health = normalize_component_health(component_health)
    factor = health['condenser'] / 100.0
    penalty = 1.0 + (1.0 - factor) * 1.8
    return float(pk_value) * penalty


def apply_health_to_teplofication(tf_results: Dict[str, float], component_health: Dict[str, float], shema_tf: int) -> Dict[str, float]:
    health = normalize_component_health(component_health)
    tf_results = dict(tf_results)
    if shema_tf == 1:
        tf_results['G_nto'] *= health['psg2'] / 100.0
    else:
        tf_results['G_vto'] *= health['psg1'] / 100.0
        tf_results['G_nto'] *= health['psg2'] / 100.0
    return tf_results


def estimate_condenser_power_loss(G_cond: float, P_k: float) -> float:
    flow_factor = max(0.0, float(G_cond) / max(condenser_loss_flow_ref, 1e-6))
    vacuum_factor = (float(P_k) - condenser_loss_pk_min) / max(condenser_loss_pk_max - condenser_loss_pk_min, 1e-9)
    vacuum_factor = float(np.clip(vacuum_factor, 0.0, 1.0))
    base_loss = condenser_loss_mw_min + (condenser_loss_mw_max - condenser_loss_mw_min) * vacuum_factor
    return base_loss * flow_factor


def get_mode_options(mode_data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'tw1': float(mode_data.get('tw1', tw1_nom)),
        'W_cw': float(mode_data.get('W', mode_data.get('W_cw', W_nom))),
        'tech_state_coeff': float(mode_data.get('tech_state_coeff', tech_state_coeff_nom)),
        'aux_power_fraction': float(mode_data.get('aux_power_fraction', aux_power_fraction_nom)),
        'fuel_price_per_gcal': float(mode_data.get('fuel_price_per_gcal', fuel_price_per_gcal_default)),
        'component_health': normalize_component_health(mode_data.get('component_health', {})),
    }


# ============================================================================
# РЕЖИМНЫЕ КАРТЫ И ВАЛИДАЦИЯ РЕЖИМОВ
# ============================================================================

def _interp_piecewise(x: float, points: List[Tuple[float, float]]) -> float:
    pts = sorted((float(px), float(py)) for px, py in points)
    x = float(x)

    if x <= pts[0][0]:
        x0, y0 = pts[0]
        x1, y1 = pts[1]
        return y0 if abs(x1 - x0) < 1e-12 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)

    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        if x0 <= x <= x1:
            return y0 if abs(x1 - x0) < 1e-12 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)

    x0, y0 = pts[-2]
    x1, y1 = pts[-1]
    return y1 if abs(x1 - x0) < 1e-12 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)



# ---- Т-режим / К-режим по табличной карте ----

# Узловые точки из документа "Теплофикационный режим.docx":
# Q отбора [Гкал/ч], G на ЦВД [т/ч], G на ЦСНД [т/ч], N [МВт]
_T_MODE_SLICE_POINTS = {
    0.0: [
        (27.0, 120.0, 100.0),
        (33.0, 140.0, 120.0),
        (40.0, 162.0, 140.0),
        (47.0, 190.0, 160.0),
        (55.0, 218.0, 180.0),
        (65.0, 252.0, 200.0),
        (71.0, 278.0, 220.0),
    ],
    30.0: [
        (30.0, 160.0, 80.0),
        (37.0, 180.0, 100.0),
        (43.0, 202.0, 120.0),
        (52.0, 237.0, 140.0),
        (58.0, 259.0, 160.0),
        (65.0, 280.0, 180.0),
        (73.0, 302.0, 200.0),
        (78.0, 329.0, 220.0),
    ],
    60.0: [
        (40.0, 221.0, 80.0),
        (48.0, 250.0, 100.0),
        (55.0, 278.0, 120.0),
        (63.0, 300.0, 140.0),
        (69.0, 322.0, 160.0),
        (75.0, 342.0, 180.0),
        (83.0, 380.0, 200.0),
        (90.0, 401.0, 220.0),
    ],
    90.0: [
        (53.0, 298.0, 80.0),
        (59.0, 320.0, 100.0),
        (66.0, 341.0, 120.0),
        (73.0, 372.0, 140.0),
        (79.0, 398.0, 160.0),
        (87.0, 420.0, 180.0),
        (93.0, 445.0, 200.0),
        (97.0, 470.0, 220.0),
    ],
    120.0: [
        (63.0, 363.0, 80.0),
        (69.0, 380.0, 100.0),
        (77.0, 418.0, 120.0),
        (83.0, 440.0, 140.0),
        (90.0, 470.0, 162.0),
    ],
    150.0: [
        (73.0, 440.0, 80.0),
        (80.0, 470.0, 110.0),
    ],
}

_T_SLICE_Q_POINTS = sorted(_T_MODE_SLICE_POINTS)
_T_NMIN_POINTS = [(q, pts[0][0]) for q, pts in sorted(_T_MODE_SLICE_POINTS.items())]
_T_NMAX_POINTS = [(q, pts[-1][0]) for q, pts in sorted(_T_MODE_SLICE_POINTS.items())]

# Область ЕПД для теплофикационного режима из документа.
_T_EPD_POINTS = {
    0.0: (73.0, 82.0),
    30.0: (80.0, 91.0),
    60.0: (91.0, 100.0),
    90.0: (98.0, 100.0),
}

# Конденсационный режим без отборов.
_K_MODE_NMIN_MW = 17.0
_K_MODE_NMAX_MW = 74.0


def _interp_on_n(points: List[Tuple[float, float, float]], n: float, value_index: int) -> float:
    pts = sorted((float(p[0]), float(p[value_index])) for p in points)
    return _interp_piecewise(float(n), pts)


def _bracket_q_slices(q: float) -> Tuple[float, float]:
    qs = _T_SLICE_Q_POINTS
    if q <= qs[0]:
        return qs[0], qs[0]
    if q >= qs[-1]:
        return qs[-1], qs[-1]
    for q0, q1 in zip(qs[:-1], qs[1:]):
        if q0 <= q <= q1:
            return q0, q1
    return qs[-1], qs[-1]


def _interp_between_q(q: float, q0: float, v0: float, q1: float, v1: float) -> float:
    if abs(q1 - q0) < 1e-12:
        return float(v0)
    return float(v0) + (float(v1) - float(v0)) * (float(q) - float(q0)) / (float(q1) - float(q0))


def _t_mode_n_bounds(q: float) -> Tuple[float, float]:
    nmin = _interp_piecewise(q, _T_NMIN_POINTS)
    nmax = _interp_piecewise(q, _T_NMAX_POINTS)
    return float(nmin), float(nmax)


def _t_mode_reference_values(q: float, n: float) -> Tuple[Optional[float], Optional[float]]:
    q0, q1 = _bracket_q_slices(float(q))
    pts0 = _T_MODE_SLICE_POINTS[q0]
    n0_min, n0_max = pts0[0][0], pts0[-1][0]
    if not (n0_min - 1e-9 <= float(n) <= n0_max + 1e-9):
        g0_0 = gcsnd_0 = None
    else:
        g0_0 = _interp_on_n(pts0, float(n), 1)
        gcsnd_0 = _interp_on_n(pts0, float(n), 2)

    if q1 == q0:
        return g0_0, gcsnd_0

    pts1 = _T_MODE_SLICE_POINTS[q1]
    n1_min, n1_max = pts1[0][0], pts1[-1][0]
    if not (n1_min - 1e-9 <= float(n) <= n1_max + 1e-9):
        g0_1 = gcsnd_1 = None
    else:
        g0_1 = _interp_on_n(pts1, float(n), 1)
        gcsnd_1 = _interp_on_n(pts1, float(n), 2)

    if g0_0 is None or g0_1 is None or gcsnd_0 is None or gcsnd_1 is None:
        return None, None

    return (
        _interp_between_q(float(q), q0, g0_0, q1, g0_1),
        _interp_between_q(float(q), q0, gcsnd_0, q1, gcsnd_1),
    )


def _t_mode_epd_bounds(q: float) -> Optional[Tuple[float, float]]:
    epd_qs = sorted(_T_EPD_POINTS)
    q = float(q)
    if q < epd_qs[0] or q > epd_qs[-1]:
        return None
    lo = _interp_piecewise(q, [(qq, rng[0]) for qq, rng in sorted(_T_EPD_POINTS.items())])
    hi = _interp_piecewise(q, [(qq, rng[1]) for qq, rng in sorted(_T_EPD_POINTS.items())])
    return float(lo), float(hi)


def evaluate_t_regime_envelope(Nz: float, Qtf: float, G0: Optional[float] = None,
                               G_to_csnd: Optional[float] = None, Gprom: float = 0.0) -> Dict[str, Any]:
    q = float(Qtf)
    n = float(Nz)
    gprom = float(Gprom)

    warnings: List[str] = []
    valid = True

    # К-режим: без теплофикационного и производственного отборов.
    if q <= 1e-9 and gprom <= 1e-9:
        if not (_K_MODE_NMIN_MW - 1e-9 <= n <= _K_MODE_NMAX_MW + 1e-9):
            valid = False
            warnings.append(
                f"Недопустимый К-режим: N={n:.1f} МВт вне диапазона [{_K_MODE_NMIN_MW:.1f}; {_K_MODE_NMAX_MW:.1f}] МВт"
            )
        return {
            "mode_family": "K",
            "valid": valid,
            "warnings": warnings,
            "nmin_ref": _K_MODE_NMIN_MW,
            "nmax_ref": _K_MODE_NMAX_MW,
            "n_margin_mw": _K_MODE_NMAX_MW - n,
            "g0_ref": None,
            "g0_delta_tph": None,
            "gcsd_ref": None,
            "gcsd_delta_tph": None,
            "epd_bounds_mw": None,
        }

    nmin_ref, nmax_ref = _t_mode_n_bounds(q)
    if n < nmin_ref - 1e-9 or n > nmax_ref + 1e-9:
        valid = False
        warnings.append(
            f"Несуществующий Т-режим: N={n:.1f} МВт вне диапазона [{nmin_ref:.1f}; {nmax_ref:.1f}] МВт при Qтф={q:.1f} Гкал/ч"
        )

    epd_bounds = _t_mode_epd_bounds(q)
    if epd_bounds is not None:
        epd_lo, epd_hi = epd_bounds
        if epd_lo - 1e-9 <= n <= epd_hi + 1e-9:
            valid = False
            warnings.append(
                f"Попадание в область ЕПД: N={n:.1f} МВт в диапазоне [{epd_lo:.1f}; {epd_hi:.1f}] МВт при Qтф={q:.1f} Гкал/ч"
            )

    g0_ref, gcsd_ref = _t_mode_reference_values(q, n)

    g0_delta = None
    if G0 is not None and g0_ref is not None:
        g0_delta = float(G0) - g0_ref
        if abs(g0_delta) > 25.0:
            warnings.append(
                f"Отклонение от табличного расхода на ЦВД: G0={float(G0):.1f} т/ч, ориентир={g0_ref:.1f} т/ч"
            )

    gcsd_delta = None
    if G_to_csnd is not None and gcsd_ref is not None:
        gcsd_delta = float(G_to_csnd) - gcsd_ref
        if abs(gcsd_delta) > 20.0:
            warnings.append(
                f"Отклонение от табличного расхода на ЦСНД: Gвх_ЦСНД={float(G_to_csnd):.1f} т/ч, ориентир={gcsd_ref:.1f} т/ч"
            )

    return {
        "mode_family": "T",
        "valid": valid,
        "warnings": warnings,
        "nmin_ref": nmin_ref,
        "nmax_ref": nmax_ref,
        "n_margin_mw": nmax_ref - n,
        "g0_ref": g0_ref,
        "g0_delta_tph": g0_delta,
        "gcsd_ref": gcsd_ref,
        "gcsd_delta_tph": gcsd_delta,
        "epd_bounds_mw": epd_bounds,
    }

# ---- ПТ-режим ----
# N_real = N_imag - 7 => N_imag = N_real + 7
_PT_NIMAG_MIN_POINTS = [
    (0.0, 40.0),
    (30.0, 40.0),
    (60.0, 37.0),
    (90.0, 50.0),
    (120.0, 60.0),
    (150.0, 72.0),
]

_PT_NIMAG_MAX_POINTS = [
    (0.0, 80.0),
    (30.0, 92.0),
    (60.0, 97.0),
    (90.0, 100.0),
    (120.0, 91.0),
    (150.0, 80.0),
]

_PT_QTF_MIN_POINTS = [
    (0.0, 28.0),
    (30.0, 28.0),
    (60.0, 28.0),
    (90.0, 28.0),
    (120.0, 28.0),
    (150.0, 28.0),
]

_PT_QTF_MAX_POINTS = [
    (0.0, 100.0),
    (30.0, 100.0),
    (60.0, 100.0),
    (90.0, 90.0),
    (120.0, 65.0),
    (150.0, 40.0),
]


def evaluate_pt_regime_envelope(N_real: float, Qprom: float, Qtf: Optional[float] = None) -> Dict[str, Any]:
    qp = float(Qprom)
    n_real = float(N_real)
    nimag = n_real + 7.0

    nimag_min_ref = _interp_piecewise(qp, _PT_NIMAG_MIN_POINTS)
    nimag_max_ref = _interp_piecewise(qp, _PT_NIMAG_MAX_POINTS)
    qtf_min_ref = _interp_piecewise(qp, _PT_QTF_MIN_POINTS)
    qtf_max_ref = _interp_piecewise(qp, _PT_QTF_MAX_POINTS)

    valid = True
    warnings: List[str] = []

    if not (nimag_min_ref - 1e-9 <= nimag <= nimag_max_ref + 1e-9):
        valid = False
        warnings.append(
            f"Недопустимый ПТ-режим: Nмним={nimag:.1f} МВт вне диапазона "
            f"[{nimag_min_ref:.1f}; {nimag_max_ref:.1f}] МВт при Qпр={qp:.1f} Гкал/ч"
        )

    if Qtf is not None:
        qtf = float(Qtf)
        if not (qtf_min_ref - 1e-9 <= qtf <= qtf_max_ref + 1e-9):
            valid = False
            warnings.append(
                f"Недопустимый ПТ-режим по теплофикационной нагрузке: Qтф={qtf:.1f} Гкал/ч вне диапазона "
                f"[{qtf_min_ref:.1f}; {qtf_max_ref:.1f}] Гкал/ч при Qпр={qp:.1f} Гкал/ч"
            )

    return {
        "mode_family": "PT",
        "valid": valid,
        "warnings": warnings,
        "nimag": nimag,
        "nimag_min_ref": nimag_min_ref,
        "nimag_max_ref": nimag_max_ref,
        "qtf_min_ref": qtf_min_ref,
        "qtf_max_ref": qtf_max_ref,
    }


# ============================================================================
# ТЕПЛОФИКАЦИЯ И НАЧАЛЬНЫЙ РАСХОД
# ============================================================================

def calc_teplofik(Qtf: float, shema_tf: int, P_vto: float, P_nto: float) -> Dict[str, float]:
    print(f"\n{'=' * 50}")
    print("РАСЧЕТ ТЕПЛОФИКАЦИИ")
    print(f"{'=' * 50}")
    print(f"Qtf = {Qtf} Гкал/ч, схема = {'одноступенчатая' if shema_tf == 1 else 'двухступенчатая'}")
    print(f"P_vto = {P_vto:.3f} МПа, P_nto = {P_nto:.3f} МПа")

    Qtf_kW = float(Qtf) * 1163.0

    if shema_tf == 1:
        r_nto = h_steam_sat(P_nto) - h_water(P_nto)
        G_nto_kg_s = Qtf_kW / r_nto if r_nto > 0 else 0.0
        G_nto = kgs_to_th(G_nto_kg_s)
        G_vto = 0.0
        K = K_odno
        print(f"  r_nto = {r_nto:.1f} кДж/кг")
        print(f"  G_nto = {G_nto:.2f} т/ч")
    else:
        r_nto = h_steam_sat(P_nto) - h_water(P_nto)
        r_vto = h_steam_sat(P_vto) - h_water(P_vto)
        if r_nto > 0 and r_vto > 0:
            G_nto_kg_s = 0.4 * Qtf_kW / r_nto
            G_vto_kg_s = 0.6 * Qtf_kW / r_vto
        else:
            G_nto_kg_s = 0.0
            G_vto_kg_s = 0.0
        G_nto = kgs_to_th(G_nto_kg_s)
        G_vto = kgs_to_th(G_vto_kg_s)
        K = K_dvuh
        print(f"  r_nto = {r_nto:.1f} кДж/кг, r_vto = {r_vto:.1f} кДж/кг")
        print(f"  G_nto = {G_nto:.2f} т/ч, G_vto = {G_vto:.2f} т/ч")

    dN_tf = K * float(Qtf)
    print(f"  Снижение мощности: ΔN_tf = {dN_tf:.2f} МВт")
    return {'G_vto': G_vto, 'G_nto': G_nto, 'dN_tf': dN_tf, 'shema': shema_tf}


def calculate_initial_G0(Nz: float, Gprom: float, Qtf: float, shema_tf: int) -> float:
    """
    Начальный расход свежего пара, привязанный к эксплуатационной характеристике.
    """
    if Nz <= 60:
        G0_base = 3.0 * float(Nz)
    else:
        G0_base = -0.025987526 * float(Nz) ** 2 + 11.9178794 * float(Nz) - 441.517672

    G0_base = max(120.0, G0_base)

    if Gprom > 200:
        k_prom = 0.60
    elif Gprom > 150:
        k_prom = 0.54
    elif Gprom > 100:
        k_prom = 0.48
    elif Gprom > 50:
        k_prom = 0.43
    else:
        k_prom = 0.38

    if shema_tf == 2:
        k_tf = 0.34 if Qtf > 80 else 0.31 if Qtf > 50 else 0.28
    else:
        k_tf = 0.29 if Qtf > 80 else 0.26 if Qtf > 50 else 0.23

    dG_prom = float(Gprom) * k_prom
    dG_tf = float(Qtf) * k_tf
    G0 = G0_base + dG_prom + dG_tf

    print(f"\n[INFO] Составляющие G0: баз={G0_base:.1f}, пром=+{dG_prom:.1f}, тф=+{dG_tf:.1f} -> {G0:.1f}")
    return G0


# ============================================================================
# ВАЛИДАЦИЯ ВХОДНЫХ ДАННЫХ
# ============================================================================


def validate_mode_data(mode_data: Dict[str, Any]) -> Tuple[float, float, float, int]:
    required_keys = ['mode_id', 'Nz', 'Gprom', 'Qtf', 'shema_tf']
    for key in required_keys:
        if key not in mode_data:
            raise ValueError(f"Отсутствует обязательный параметр: {key}")

    try:
        Nz = float(mode_data['Nz'])
        Gprom = float(mode_data['Gprom'])
        Qtf = float(mode_data['Qtf'])
        shema_tf = int(mode_data['shema_tf'])
        Qprom = float(mode_data.get('Qprom', 0.0) or 0.0)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Ошибка преобразования параметров: {e}")

    n_min_allowed = min(float(N_min), _K_MODE_NMIN_MW)
    n_max_allowed = max(float(N_max), 100.0)
    qtf_max_allowed = max(float(Qtf_max), 150.0)

    if not (n_min_allowed <= Nz <= n_max_allowed):
        raise ValueError(f"Мощность Nz={Nz} вне диапазона [{n_min_allowed}, {n_max_allowed}] МВт")
    if not (0 <= Gprom <= Gprom_max):
        raise ValueError(f"Производственный отбор Gprom={Gprom} вне диапазона [0, {Gprom_max}] т/ч")
    if not (0 <= Qprom <= Gprom_max):
        raise ValueError(f"Тепловая нагрузка промотбора Qprom={Qprom} вне диапазона [0, {Gprom_max}] Гкал/ч")
    if not (0 <= Qtf <= qtf_max_allowed):
        raise ValueError(f"Теплофикационная нагрузка Qtf={Qtf} вне диапазона [0, {qtf_max_allowed}] Гкал/ч")
    if shema_tf not in [1, 2]:
        raise ValueError(f"Схема теплофикации shema_tf={shema_tf} должна быть 1 или 2")

    return Nz, Gprom, Qtf, shema_tf


# ============================================================================
# СБОРКА ДАННЫХ КОМПОНЕНТОВ
# ============================================================================

def build_components_data(results: Dict[str, Any], cvd_pressures: Dict[str, Any],
                          csnd_pressures: Dict[str, Any], cond_results: Dict[str, Any],
                          reg_results: Dict[str, Any]) -> Dict[str, Any]:
    t_sat_1 = ts(results['P1'])
    t_sat_2 = ts(results['P2'])
    t_sat_3 = ts(results['P3'])
    t_sat_vto = ts(results['P_vto']) if results['P_vto'] > 0 else 0.0
    t_sat_nto = ts(results['P_nto']) if results['P_nto'] > 0 else 0.0
    t_sat_cond = ts(results['P_k'])

    components = {
        'cvd': {
            'name': 'ЦВД (Цилиндр ВД)',
            'data': [
                ('Мощность N_cvd', f"{results['N_cvd']:.1f}", 'МВт'),
                ('Расход на входе G₀', f"{results['G0']:.1f}", 'т/ч'),
                ('Давление входа P₀', f"{P0:.1f}", 'МПа'),
                ('Температура входа t₀', f"{t0:.0f}", '°C'),
                ('Давл. в отборе 1 (ПВД-7) P₁', f"{results['P1']:.3f}", 'МПа'),
                ('Темп. в отборе 1', f"{t_sat_1:.0f}", '°C'),
                ('Давл. в отборе 2 (ПВД-6) P₂', f"{results['P2']:.3f}", 'МПа'),
                ('Темп. в отборе 2', f"{t_sat_2:.0f}", '°C'),
                ('Давл. в отборе 3 (ПВД-5) P₃', f"{results['P3']:.3f}", 'МПа'),
                ('Темп. в отборе 3', f"{t_sat_3:.0f}", '°C'),
                ('Давл. на выходе P_пром', f"{results['P_prom']:.3f}", 'МПа'),
                ('КПД отсеков η_oi', '80-86', '%'),
            ],
        },
        'csnd': {
            'name': 'ЦСНД (Цилиндр НД)',
            'data': [
                ('Мощность N_csnd', f"{results['N_csnd']:.1f}", 'МВт'),
                ('Расход на входе G_вх', f"{results.get('G_to_csnd', 0.0):.1f}", 'т/ч'),
                ('Давл. входа (пром.) P_вх', f"{results['P_prom']:.3f}", 'МПа'),
                ('Давл. ВТО P_вто', f"{results['P_vto']:.3f}", 'МПа'),
                ('Темп. ВТО t_вто', f"{t_sat_vto:.0f}", '°C'),
                ('Давл. НТО P_нто', f"{results['P_nto']:.3f}", 'МПа'),
                ('Темп. НТО t_нто', f"{t_sat_nto:.0f}", '°C'),
                ('Давл. выхода P_вых', f"{results['P_k']:.4f}", 'МПа'),
                ('Расход в конденсатор G_к', f"{results['G_cond']:.1f}", 'т/ч'),
                ('КПД отсеков η_oi', '78-83', '%'),
            ],
        },
        'condenser': {
            'name': 'Конденсатор',
            'data': [
                ('Давление P_к', f"{results['P_k'] * 1000:.1f}", 'кПа'),
                ('Темп. насыщения t_s', f"{t_sat_cond:.1f}", '°C'),
                ('Расход пара G_к', f"{results['G_cond']:.1f}", 'т/ч'),
                ('Темп. воды на входе t_в1', f"{results.get('tw1', tw1_nom):.1f}", '°C'),
                ('Расход охл. воды W', f"{results.get('W_cw_effective', results.get('W_cw', W_nom)):.0f}", 'м³/ч'),
                ('Поверхность охлажд. F_к', f"{Fk:.0f}", 'м²'),
                ('Недовыработка ΔN_вак', f"{results.get('dN_cond', 0.0):.2f}", 'МВт'),
            ],
        },
        'pvd7': {
            'name': 'ПВД-7 (Подогр. ВД №7)',
            'data': [
                ('Расход греющего пара G₁', f"{results['G1']:.2f}", 'т/ч'),
                ('Давление пара P₁', f"{results['P1']:.3f}", 'МПа'),
                ('Темп. насыщения t_s1', f"{t_sat_1:.0f}", '°C'),
                ('Темп. воды на входе', f"{results['t_ok']:.1f}", '°C'),
                ('Темп. воды на выходе', f"{results['t_pv']:.1f}", '°C'),
                ('Нагрев воды Δt', f"{results['t_pv'] - results['t_ok']:.1f}", '°C'),
                ('Недогрев Δt_нед', f"{dt_ned_PVD:.1f}", '°C'),
            ],
        },
        'pvd6': {
            'name': 'ПВД-6 (Подогр. ВД №6)',
            'data': [
                ('Расход греющего пара G₂', f"{results['G2']:.2f}", 'т/ч'),
                ('Давление пара P₂', f"{results['P2']:.3f}", 'МПа'),
                ('Темп. насыщения t_s2', f"{t_sat_2:.0f}", '°C'),
                ('Темп. воды на входе', f"{results['t_ok']:.1f}", '°C'),
                ('Недогрев Δt_нед', f"{dt_ned_PVD:.1f}", '°C'),
            ],
        },
        'pvd5': {
            'name': 'ПВД-5 (Подогр. ВД №5)',
            'data': [
                ('Расход греющего пара G₃', f"{results['G3']:.2f}", 'т/ч'),
                ('Давление пара P₃', f"{results['P3']:.3f}", 'МПа'),
                ('Темп. насыщения t_s3', f"{t_sat_3:.0f}", '°C'),
                ('Недогрев Δt_нед', f"{dt_ned_PVD:.1f}", '°C'),
                ('Температура питательной воды', f"{results['t_pv']:.1f}", '°C'),
            ],
        },
        'deaerator': {
            'name': 'Деаэратор Д-6',
            'data': [
                ('Давление P_д', f"{Pd:.2f}", 'МПа'),
                ('Темп. насыщения t_s', f"{ts_d:.1f}", '°C'),
                ('Расход на выходе G_пв', f"{results['G_pv']:.1f}", 'т/ч'),
                ('Расход греющего пара', f"{results['G_steam_d']:.2f}", 'т/ч'),
                ('Расход возврата', f"{results['Gprom'] * beta_vozvrat:.1f}", 'т/ч'),
            ],
        },
        'pnd_group': {
            'name': 'ПНД (Подогреватели НД)',
            'data': [
                ('ПНД-4: G₄', f"{results['G4']:.2f}", 'т/ч'),
                ('ПНД-3: G₅', f"{results['G5']:.2f}", 'т/ч'),
                ('ПНД-2: G₆', f"{results['G6']:.2f}", 'т/ч'),
                ('ПНД-1: G₇', f"{results['G7']:.2f}", 'т/ч'),
            ],
        },
        'heat_network': {
            'name': 'Тепловая сеть',
            'data': [
                ('Расход ВТО G_вто', f"{results['G_vto']:.2f}", 'т/ч'),
                ('Давление ВТО P_вто', f"{results['P_vto']:.3f}", 'МПа'),
                ('Расход НТО G_нто', f"{results['G_nto']:.2f}", 'т/ч'),
                ('Давление НТО P_нто', f"{results['P_nto']:.3f}", 'МПа'),
                ('Тепловая нагрузка Q_тф', f"{results['Qtf']:.1f}", 'Гкал/ч'),
                ('Схема теплоф.', f"{'одноступ.' if results['shema_tf'] == 1 else 'двухступ.'}", '-'),
            ],
        },
        'generator': {
            'name': 'Генератор',
            'data': [
                ('Брутто мощность N_эл', f"{results['N_el_gross']:.1f}", 'МВт'),
                ('Факт. мощность после вакуума', f"{results['N_el_actual']:.1f}", 'МВт'),
                ('Нетто мощность N_нетто', f"{results['N_el_net']:.1f}", 'МВт'),
                ('Собственные нужды', f"{results['N_aux']:.1f}", 'МВт'),
                ('Напряжение U', '10.5', 'кВ'),
                ('Частота f', '50', 'Гц'),
            ],
        },
        'overall': {
            'name': 'Общие показатели',
            'data': [
                ('Запрос мощности Nz', f"{results['Nz']:.1f}", 'МВт'),
                ('Расход свежего пара G₀', f"{results['G0']:.1f}", 'т/ч'),
                ('Производительность Q₀', f"{results['Q0']:.1f}", 'Гкал/ч'),
                ('Производствен. отбор Gprom', f"{results['Gprom']:.1f}", 'т/ч'),
                ('Тепл. нагрузка пром. отбора Qprom', f"{results.get('Qprom', 0.0):.1f}", 'Гкал/ч'),
                ('КПД брутто η_брутто', f"{results['eta_brut']:.1f}", '%'),
                ('КПД нетто η_нетто', f"{results['eta_net']:.1f}", '%'),
                ('Удельный расход тепла q_t', f"{results['q_t']:.0f}", 'ккал/кВт·ч'),
                ('q_t нетто', f"{results['q_t_net']:.0f}", 'ккал/кВт·ч'),
                ('Сходимость (итерации)', f"{results['iterations']}", 'шт.'),
                ('Невязка баланса', f"{abs(results['delta_balance']):.3f}", 'т/ч'),
            ],
        },
    }

    health = results.get('component_health', {})
    for key, comp_key in [('cvd', 'cvd'), ('csnd', 'csnd'), ('condenser', 'condenser'), ('generator', 'generator'), ('pvd7', 'pvd7'), ('pvd6', 'pvd6'), ('pvd5', 'pvd5')]:
        if key in components and comp_key in health:
            components[key]['data'].append(('Целостность', f"{health[comp_key]:.1f}", '%'))

    if results.get('fuel_cost_per_hour', 0) > 0:
        components['overall']['data'].extend([
            ('Топливная себестоимость/ч', f"{results['fuel_cost_per_hour']:.0f}", 'руб/ч'),
            ('Себест. брутто', f"{results['fuel_cost_per_mwh_gross']:.0f}", 'руб/МВт·ч'),
            ('Себест. нетто', f"{results['fuel_cost_per_mwh_net']:.0f}", 'руб/МВт·ч'),
        ])

    if not results.get('regime_valid', True):
        for msg in results.get('regime_warnings', []):
            components['overall']['data'].append(('Предупреждение', msg, ''))

    return components


# ============================================================================
# ОСНОВНАЯ ФУНКЦИЯ РАСЧЁТА
# ============================================================================

def calculate_mode(mode_data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        Nz, Gprom, Qtf, shema_tf = validate_mode_data(mode_data)
        mode_id = mode_data['mode_id']
    except ValueError as e:
        raise ValueError(f"[ERROR] Ошибка валидации входных данных: {e}")

    options = get_mode_options(mode_data)
    tw1 = options['tw1']
    W_cw = options['W_cw']
    tech_state_coeff = options['tech_state_coeff']
    aux_power_fraction = options['aux_power_fraction']
    fuel_price_per_gcal = options['fuel_price_per_gcal']
    component_health = options['component_health']

    critical_health = validate_critical_component_health(component_health)
    if not critical_health["valid"]:
        raise RuntimeError(critical_health["message"])

    print_separator(f"РЕЖИМ {mode_id}: Nz={Nz} МВт, Gprom={Gprom} т/ч, Qtf={Qtf} Гкал/ч")
    print(f"[INFO] Параметры конденсатора: tw1={tw1:.1f}°C, W={W_cw:.0f} м³/ч")
    print(f"[INFO] Коэф. техсостояния={tech_state_coeff:.3f}, собств. нужды={aux_power_fraction*100:.1f}%")
    print(f"[INFO] Состояние оборудования: {component_health}")

    G0 = calculate_initial_G0(Nz, Gprom, Qtf, shema_tf)

    # Начальные оценки отборов
    G1 = max(2.0, 0.025 * G0)
    G2 = max(3.0, 0.030 * G0)
    G3 = max(6.0, 0.050 * G0)

    if Qtf > 0:
        G4 = max(2.0, 0.015 * G0)
        G5 = max(2.0, 0.012 * G0)
        G6 = max(1.5, 0.010 * G0)
        G7 = max(1.5, 0.010 * G0)
    else:
        G4 = G5 = G6 = G7 = 0.0

    G_vto = 0.0
    G_nto = 0.0
    dN_tf = 0.0
    history: List[Dict[str, float]] = []

    print("\n[START] Начало итерационного расчета (макс. 15 итераций)")

    for iteration in range(15):
        try:
            print(f"\n{'=' * 80}")
            print(f"ИТЕРАЦИЯ {iteration + 1}")
            print(f"{'=' * 80}")
            print(f"G0 = {G0:.1f} т/ч")

            cvd_pressures = calc_pressures_cvd(G0, G1, G2, G3)
            N_cvd, h_prom, cvd_enthalpies = calc_power_cvd(G0, G1, G2, G3, cvd_pressures)
            if not np.isfinite(N_cvd) or not np.isfinite(h_prom):
                raise RuntimeError(f"Расчет ЦВД дал бесконечные значения: N_cvd={N_cvd}, h_prom={h_prom}")

            csnd_pressures = calc_pressures_csnd_full(
                cvd_pressures['G_cvd_out'],
                Gprom,
                G4, G5, G6, G7,
                G_vto, G_nto,
                cvd_pressures['P_prom'],
            )

            csnd_enthalpies = calc_h_values_csnd(csnd_pressures, h_prom, x_start=0.98)

            if Qtf > 0:
                tf_results = calc_teplofik(Qtf, shema_tf, csnd_pressures['P_vto'], csnd_pressures['P_nto'])
                tf_results = apply_health_to_teplofication(tf_results, component_health, shema_tf)
                G_vto, G_nto = tf_results['G_vto'], tf_results['G_nto']
                dN_tf = tf_results['dN_tf']
            else:
                G_vto = 0.0
                G_nto = 0.0
                dN_tf = 0.0

            h_k_pre = csnd_enthalpies['h_k']
            W_cw_effective = W_cw * (component_health['condenser'] / 100.0)
            cond_results = calc_condenser(csnd_pressures['G_k'], h_k_pre, W_cw_effective, tw1)
            cond_results['W_effective'] = W_cw_effective
            cond_results['P_k'] = apply_health_to_condenser(cond_results['P_k'], component_health)

            # Возвращаем фактическое давление конденсатора обратно в ЦСНД
            csnd_pressures['P_k'] = cond_results['P_k']
            csnd_enthalpies = calc_h_values_csnd(csnd_pressures, h_prom, x_start=0.98)

            G_ok = max(0.0, G0 - G1 - G2 - G3 - G4 - G5 - G6 - G7 - Gprom - G_vto - G_nto)
            t_k = cond_results['tsat'] + 3.0
            G_return = Gprom * beta_vozvrat

            reg_results = calc_regeneration_full(
                cvd_pressures,
                csnd_pressures,
                csnd_enthalpies,
                G_ok,
                t_k,
                G_return,
                t_vozvrat,
            )

            scaled_flows = apply_component_health_to_flows(component_health, {
                'G1': reg_results.get('G1', G1),
                'G2': reg_results.get('G2', G2),
                'G3': reg_results.get('G3', G3),
                'G4': reg_results.get('G4', G4),
                'G5': reg_results.get('G5', G5),
                'G6': reg_results.get('G6', G6),
                'G7': reg_results.get('G7', G7),
                'G_steam_d': reg_results.get('G_steam_d', 0.0),
            })
            G1 = scaled_flows['G1']
            G2 = scaled_flows['G2']
            G3 = scaled_flows['G3']
            G4 = scaled_flows['G4']
            G5 = scaled_flows['G5']
            G6 = scaled_flows['G6']
            G7 = scaled_flows['G7']
            G_steam_d = scaled_flows['G_steam_d']

            N_csnd = calc_power_csnd_full(
                h_prom,
                csnd_enthalpies['h4'], csnd_enthalpies['h5'], csnd_enthalpies['h6'], csnd_enthalpies['h7'],
                csnd_enthalpies['h_vto'], csnd_enthalpies['h_nto'], csnd_enthalpies['h_k'],
                cvd_pressures['G_cvd_out'],
                Gprom,
                G4, G5, G6, G7,
                G_vto, G_nto,
                eta_oi_csnd_full,
            )

            N_cvd_eff = N_cvd * component_health['cvd'] / 100.0
            N_csnd_eff = N_csnd * component_health['csnd'] / 100.0
            generator_factor = component_health['generator'] / 100.0
            N_el_gross_calc = (N_cvd_eff + N_csnd_eff) * etam * etag_nom * tech_state_coeff * generator_factor

            G_otbory = G1 + G2 + G3 + G4 + G5 + G6 + G7 + G_steam_d + Gprom + G_vto + G_nto
            G_cond = max(0.0, G0 - G_otbory)
            delta_balance = G0 - (G_otbory + G_cond)

            history.append({
                'iter': iteration + 1,
                'G0': G0,
                'N_el': N_el_gross_calc,
                'delta': delta_balance,
                'P_k': cond_results['P_k'] * 1000.0,
                'G_cond': G_cond,
            })

            print(f"\n[RESULT] РЕЗУЛЬТАТЫ ИТЕРАЦИИ {iteration + 1}:")
            print(f"  N_cvd = {N_cvd_eff:.2f} МВт")
            print(f"  N_csnd = {N_csnd_eff:.2f} МВт")
            print(f"  N_el(gross) = {N_el_gross_calc:.2f} МВт (цель {Nz} МВт)")
            print(f"  G_cond = {G_cond:.1f} т/ч")
            print(f"  P_k = {cond_results['P_k'] * 1000:.1f} кПа")
            print(f"  Сумма отборов = {G_otbory:.1f} т/ч")
            print(f"  Невязка баланса = {delta_balance:.4f} т/ч")

            power_error = abs(N_el_gross_calc - Nz)
            balance_error = abs(delta_balance)

            if power_error < 0.5 and balance_error < 1.0 and iteration > 2:
                print(f"\n[OK] СХОДИМОСТЬ ДОСТИГНУТА на итерации {iteration + 1}!")
                print(f"   Погрешность по мощности: {power_error:.2f} МВт")
                print(f"   Невязка баланса: {balance_error:.3f} т/ч")
                break
            else:
                if power_error > 0.3:
                    G0_new = G0 * (Nz / max(N_el_gross_calc, 1e-6))
                    G0 = max(G0 * 0.92, min(G0 * 1.08, G0_new))
                    print(f"  Коррекция G0: {G0:.1f} т/ч")

        except KeyError as e:
            print(f"[ERROR] Отсутствует ключ в словаре результатов на итерации {iteration + 1}: {e}")
            raise RuntimeError(f"Ошибка структуры данных на итерации {iteration + 1}: {e}")
        except Exception as e:
            print(f"[ERROR] Непредвиденная ошибка на итерации {iteration + 1}: {e}")
            raise RuntimeError(f"Ошибка расчета на итерации {iteration + 1}: {e}")

    if len(history) == 15:
        print("\n[WARN] ВНИМАНИЕ: Расчет не сошелся после 15 итераций!")
        print(f"  Последняя невязка баланса: {history[-1]['delta']:.4f} т/ч")
        print(f"  Последняя ошибка по мощности: {abs(history[-1]['N_el'] - Nz):.2f} МВт")

    # Энергетические показатели
    h0 = h_steam(P0, t0)
    h_pv = h_water_temp(reg_results.get('t_pv', 249.0))
    Q0_kW = th_to_kgs(G0) * (h0 - h_pv)
    Q0_Gcal = Q0_kW / 1163.0

    N_el_gross = max(1e-6, N_el_gross_calc)
    dN_cond = estimate_condenser_power_loss(G_cond, cond_results['P_k'])
    N_el_actual = max(0.0, N_el_gross - dN_cond)
    N_aux = max(0.0, N_el_actual * aux_power_fraction)
    N_el_net = max(0.0, N_el_actual - N_aux)

    q_t = Q0_kW / (N_el_gross * 1000.0) * 3600.0 / 4.19 if N_el_gross > 0 else 0.0
    q_t_net = Q0_kW / (N_el_net * 1000.0) * 3600.0 / 4.19 if N_el_net > 0 else 0.0
    eta_brut = N_el_gross * 1000.0 / Q0_kW * 100.0 if Q0_kW > 0 else 0.0
    eta_net = N_el_net * 1000.0 / Q0_kW * 100.0 if Q0_kW > 0 else 0.0

    fuel_cost_per_hour = Q0_Gcal * fuel_price_per_gcal if fuel_price_per_gcal > 0 else 0.0
    fuel_cost_per_mwh_gross = fuel_cost_per_hour / max(N_el_gross, 1e-6) if fuel_cost_per_hour > 0 else 0.0
    fuel_cost_per_mwh_net = fuel_cost_per_hour / max(N_el_net, 1e-6) if fuel_cost_per_hour > 0 else 0.0

    # Валидация режимов
    G_to_csnd = max(0.0, float(cvd_pressures.get('G_cvd_out', 0.0)) - float(Gprom))
    regime_info = evaluate_t_regime_envelope(Nz, Qtf, G0=G0, G_to_csnd=G_to_csnd, Gprom=Gprom)

    Qprom = float(mode_data.get('Qprom', 0.0) or 0.0)
    pt_regime_info = evaluate_pt_regime_envelope(Nz, Qprom, Qtf=Qtf) if Qprom > 0.0 else None

    regime_valid = bool(regime_info.get('valid', True))
    regime_warnings = list(regime_info.get('warnings') or [])

    if pt_regime_info is not None:
        regime_valid = regime_valid and bool(pt_regime_info.get('valid', True))
        regime_warnings.extend(pt_regime_info.get('warnings') or [])

    if not regime_valid:
        msg = "\n".join(regime_warnings or [
            f"Недопустимый режим: вход в область ЕПД / выход за эксплуатационную огибающую "
            f"(N={float(Nz):.1f} МВт, Qтф={float(Qtf):.1f} Гкал/ч)"
        ])
        raise RuntimeError(msg)

    # ПСГ
    t_water_in = float(mode_data.get('t_water_in', 50.0))
    g_water_psg = mode_data.get('G_water_psg', None)
    psg_results = calc_psg(Qtf, shema_tf, t_water_in=t_water_in, G_water=g_water_psg)

    psg1_health = float(component_health.get('psg1', 100.0))
    psg2_health = float(component_health.get('psg2', 100.0))
    qtf_factor = psg2_health if shema_tf == 1 else min(psg1_health, psg2_health)

    results = {
        'mode_id': mode_id,
        'Nz': Nz,
        'Gprom': Gprom,
        'Qprom': round(Qprom, 3),
        'Qtf': Qtf,
        'shema_tf': shema_tf,
        'tw1': tw1,
        'W_cw': W_cw,
        'W_cw_effective': round(cond_results.get('W_effective', W_cw), 1),
        'tech_state_coeff': tech_state_coeff,
        'aux_power_fraction': aux_power_fraction,
        'fuel_price_per_gcal': fuel_price_per_gcal,
        'component_health': component_health,

        'G0': round(G0, 1),
        'Q0': round(Q0_Gcal, 1),
        'q_t': round(q_t, 0),
        'q_t_net': round(q_t_net, 0),
        'eta_brut': round(eta_brut, 1),
        'eta_net': round(eta_net, 1),

        'P1': round(cvd_pressures.get('P1', 4.12), 3),
        'P2': round(cvd_pressures.get('P2', 2.72), 3),
        'P3': round(cvd_pressures.get('P3', 1.30), 3),
        'P_prom': round(cvd_pressures.get('P_prom', 1.20), 3),
        'P4': round(csnd_pressures.get('P4', 0.658), 3),
        'P5': round(csnd_pressures.get('P5', 0.259), 3),
        'P6': round(csnd_pressures.get('P6', 0.098), 3),
        'P7': round(csnd_pressures.get('P7', 0.049), 3),
        'P_vto': round(csnd_pressures.get('P_vto', 0.12), 3),
        'P_nto': round(csnd_pressures.get('P_nto', 0.09), 3),
        'P_k': round(cond_results['P_k'], 4),

        't_pv': round(reg_results.get('t_pv', 249), 1),
        't_ok': round(reg_results.get('t_ok', 31), 1),

        'G1': round(G1, 2),
        'G2': round(G2, 2),
        'G3': round(G3, 2),
        'G4': round(G4, 2),
        'G5': round(G5, 2),
        'G6': round(G6, 2),
        'G7': round(G7, 2),
        'G_steam_d': round(reg_results.get('G_steam_d', 0), 2),
        'G_vto': round(G_vto, 2),
        'G_nto': round(G_nto, 2),
        'G_cond': round(G_cond, 1),
        'G_pv': round(reg_results.get('G_pv', G0), 1),

        'N_cvd': round(N_cvd_eff, 2),
        'N_csnd': round(N_csnd_eff, 2),
        'N_el_calc': round(N_el_gross, 2),
        'N_el_gross': round(N_el_gross, 2),
        'dN_cond': round(dN_cond, 2),
        'N_el_actual': round(N_el_actual, 2),
        'N_aux': round(N_aux, 2),
        'N_el_net': round(N_el_net, 2),
        'dN_tf': round(dN_tf, 2),
        'Qtf_effective': round(Qtf * (qtf_factor / 100.0), 2),

        't_water_in': round(t_water_in, 1),
        'G_water_psg': None if g_water_psg is None else float(g_water_psg),

        'G_to_csnd': round(G_to_csnd, 2),
        'regime_mode_family': regime_info.get('mode_family', 'T'),
        'regime_valid': bool(regime_valid),
        'regime_warnings': list(regime_warnings),
        't_regime_nmax_ref': regime_info.get('nmax_ref'),
        't_regime_n_margin_mw': regime_info.get('n_margin_mw'),
        't_regime_g0_ref': regime_info.get('g0_ref'),
        't_regime_g0_delta_tph': regime_info.get('g0_delta_tph'),
        't_regime_gcsd_ref': regime_info.get('gcsd_ref'),
        't_regime_gcsd_delta_tph': regime_info.get('gcsd_delta_tph'),
        'N_imag': round((pt_regime_info.get('nimag') if pt_regime_info else (Nz + 7.0)), 3),
        'pt_nimag_min_ref': None if pt_regime_info is None else pt_regime_info.get('nimag_min_ref'),
        'pt_nimag_max_ref': None if pt_regime_info is None else pt_regime_info.get('nimag_max_ref'),
        'pt_qtf_min_ref': None if pt_regime_info is None else pt_regime_info.get('qtf_min_ref'),
        'pt_qtf_max_ref': None if pt_regime_info is None else pt_regime_info.get('qtf_max_ref'),

        'fuel_cost_per_hour': round(fuel_cost_per_hour, 2),
        'fuel_cost_per_mwh_gross': round(fuel_cost_per_mwh_gross, 2),
        'fuel_cost_per_mwh_net': round(fuel_cost_per_mwh_net, 2),

        'delta_balance': round(delta_balance, 3),
        'iterations': len(history),
        'history': history,
    }

    results.update(psg_results)

    print("\n[SUMMARY] СВОДКА РЕЗУЛЬТАТОВ:")
    print(f"  G₀ = {results['G0']} т/ч")
    print(f"  Gк = {results['G_cond']} т/ч")
    print(f"  Q₀ = {results['Q0']} Гкал/ч")
    print(f"  qₜ(брутто) = {results['q_t']} ккал/кВт·ч")
    print(f"  qₜ(нетто) = {results['q_t_net']} ккал/кВт·ч")
    print(f"  КПД брутто = {results['eta_brut']:.1f}%")
    print(f"  КПД нетто = {results['eta_net']:.1f}%")
    print(f"  Pк = {results['P_k'] * 1000:.1f} кПа")
    print(f"  ΔN вакуум/хвост = {results['dN_cond']:.2f} МВт")
    print(f"  N брутто = {results['N_el_gross']:.2f} МВт")
    print(f"  N факт = {results['N_el_actual']:.2f} МВт")
    print(f"  N нетто = {results['N_el_net']:.2f} МВт")

    try:
        components_data = build_components_data(results, cvd_pressures, csnd_pressures, cond_results, reg_results)
        results['components'] = components_data
        print(f"\n[OK] Данные {len(components_data)} компонентов собраны для интерфейса")
    except Exception as e:
        print(f"\n[WARN] Предупреждение: Не удалось собрать данные компонентов: {e}")
        results['components'] = {}

    return results


if __name__ == "__main__":
    test_mode = {
        'mode_id': 'TEST',
        'Nz': 60,
        'Gprom': 0,
        'Qprom': 0,
        'Qtf': 0,
        'shema_tf': 1,
    }
    result = calculate_mode(test_mode)
    print(f"\nТест завершен. G0 = {result['G0']} т/ч")
