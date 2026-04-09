"""
cvad.py - Расчет цилиндра высокого давления (ЦВД) турбины ПТ-80/100-130/13.

Исправление: вместо плохо откалиброванного закона Стодолы используется
эмпирическая характеристика, привязанная к эксплуатационной диаграмме (ЭХ).
Это соответствует замечанию из памятки: сначала модель должна совпадать с ЭХ,
а уже потом можно добавлять поправки на техсостояние.
"""

import numpy as np
from steam_properties import h_steam
from config import P0, t0, eta_oi_cvd


P_REF = {
    'P1': 4.12,
    'P2': 2.72,
    'P3': 1.30,
    'P_prom': 1.20,
}
G_REF = {
    'P1': 300.0,
    'P2': 280.0,
    'P3': 255.0,
    'P_prom': 230.0,
}


def _pressure_from_characteristic(p_ref, g_section, g_ref, exponent=0.18, low=0.75, high=1.22):
    ratio = g_ref / max(g_section, 1.0)
    scale = np.clip(ratio ** exponent, low, high)
    return p_ref * scale


def calc_pressures_cvd(G0, G1, G2, G3):
    """Расчет давлений в отборах ЦВД по ЭХ-ориентированной характеристике."""
    print(f"\n{'=' * 60}")
    print("РАСЧЕТ ЦИЛИНДРА ВЫСОКОГО ДАВЛЕНИЯ (ЦВД)")
    print(f"{'=' * 60}")
    print(f"G0 = {G0:.1f} т/ч - расход свежего пара")
    print(f"G1 = {G1:.1f} т/ч - отбор на ПВД-7")
    print(f"G2 = {G2:.1f} т/ч - отбор на ПВД-6")
    print(f"G3 = {G3:.1f} т/ч - отбор на ПВД-5")

    G_ots1 = max(1.0, G0)
    G_ots2 = max(1.0, G0 - G1)
    G_ots3 = max(1.0, G0 - G1 - G2)
    G_ots4 = max(1.0, G0 - G1 - G2 - G3)

    P1 = _pressure_from_characteristic(P_REF['P1'], G_ots1, G_REF['P1'])
    P2 = min(P1 * 0.82, _pressure_from_characteristic(P_REF['P2'], G_ots2, G_REF['P2']))
    P3 = min(P2 * 0.62, _pressure_from_characteristic(P_REF['P3'], G_ots3, G_REF['P3']))
    P_prom = min(P3 * 0.96, _pressure_from_characteristic(P_REF['P_prom'], G_ots4, G_REF['P_prom']))

    P1 = float(np.clip(P1, 3.6, 5.4))
    P2 = float(np.clip(P2, 2.1, 3.4))
    P3 = float(np.clip(P3, 1.0, 1.8))
    P_prom = float(np.clip(P_prom, 0.95, 1.5))

    print("\n📊 ЭМПИРИЧЕСКАЯ ПРИВЯЗКА К ЭХ:")
    print(f"P1 = {P1:.3f} МПа")
    print(f"P2 = {P2:.3f} МПа")
    print(f"P3 = {P3:.3f} МПа")
    print(f"P_prom = {P_prom:.3f} МПа")
    print(f"G_cvd_out = {G_ots4:.1f} т/ч")

    return {
        'P1': P1,
        'P2': P2,
        'P3': P3,
        'P_prom': P_prom,
        'G_cvd_out': G_ots4,
    }


def calc_power_cvd(G0, G1, G2, G3, pressures):
    """Расчет внутренней мощности ЦВД."""
    print(f"\n{'=' * 60}")
    print("РАСЧЕТ МОЩНОСТИ ЦВД")
    print(f"{'=' * 60}")

    P0_inlet = P0 * 0.95
    h0 = h_steam(P0_inlet, t0)

    P1 = pressures['P1']
    P2 = pressures['P2']
    P3 = pressures['P3']
    P_prom = pressures['P_prom']

    # Температуры по типовой характеристике проточной части
    t1 = np.clip(380 + 35 * (P1 - 4.0), 360, 430)
    t2 = np.clip(320 + 25 * (P2 - 2.5), 300, 360)
    t3 = np.clip(245 + 30 * (P3 - 1.3), 220, 290)
    t_prom = np.clip(190 + 20 * (P_prom - 1.2), 165, 230)

    h1 = h_steam(P1, t1)
    h2 = h_steam(P2, t2)
    h3 = h_steam(P3, t3)
    h_prom = h_steam(P_prom, t_prom)

    print("\n📊 ЭНТАЛЬПИИ В ОТБОРАХ:")
    print(f"h0 = {h0:.1f} кДж/кг")
    print(f"h1 = {h1:.1f} кДж/кг")
    print(f"h2 = {h2:.1f} кДж/кг")
    print(f"h3 = {h3:.1f} кДж/кг")
    print(f"h_prom = {h_prom:.1f} кДж/кг")

    kgs = 1000 / 3600
    G0_kgs = G0 * kgs
    G1_kgs = G1 * kgs
    G2_kgs = G2 * kgs
    G3_kgs = G3 * kgs

    dH1 = max(0.0, h0 - h1)
    dH2 = max(0.0, h1 - h2)
    dH3 = max(0.0, h2 - h3)
    dH4 = max(0.0, h3 - h_prom)

    N1 = G0_kgs * dH1 * eta_oi_cvd[0] / 1000
    N2 = max(0.0, G0_kgs - G1_kgs) * dH2 * eta_oi_cvd[1] / 1000
    N3 = max(0.0, G0_kgs - G1_kgs - G2_kgs) * dH3 * eta_oi_cvd[2] / 1000
    N4 = max(0.0, G0_kgs - G1_kgs - G2_kgs - G3_kgs) * dH4 * eta_oi_cvd[3] / 1000

    N_total = N1 + N2 + N3 + N4

    print("\n📊 МОЩНОСТЬ ОТСЕКОВ:")
    print(f"N1 = {N1:.2f} МВт")
    print(f"N2 = {N2:.2f} МВт")
    print(f"N3 = {N3:.2f} МВт")
    print(f"N4 = {N4:.2f} МВт")
    print(f"ΣN_ЦВД = {N_total:.2f} МВт")

    enthalpies = {
        'h1': h1,
        'h2': h2,
        'h3': h3,
        'h_prom': h_prom,
    }
    return N_total, h_prom, enthalpies
