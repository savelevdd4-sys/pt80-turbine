# csnd.py
"""
csnd.py - Расчет цилиндра среднего и низкого давления (ЦСНД) турбины ПТ-80/100-130/13.

Исправление: вместо неустойчивого расчета по закону Стодолы используется
эмпирическая лестница давлений, привязанная к эксплуатационной характеристике
и фактическому расходу в хвост. Давление в конденсаторе затем уточняется в cnd.py.
"""

import numpy as np
from config import eta_oi_csnd_full
from steam_properties import ts, h_steam_sat, h_water


def _scale(g_ref, g_value, exponent=0.12, low=0.82, high=1.18):
    ratio = g_ref / max(g_value, 1.0)
    return float(np.clip(ratio ** exponent, low, high))


def calc_pressures_csnd_full(G_in, G_prom, G4, G5, G6, G7, G_vto, G_nto, P_prom):
    """ЭХ-ориентированный расчет давлений в отборах ЦСНД."""
    print(f"\n{'=' * 60}")
    print("ПОЛНЫЙ РАСЧЕТ ЦСНД (давления в отборах)")
    print(f"{'=' * 60}")
    print(f"G_in = {G_in:.1f} т/ч (вход в ЦСНД)")
    print(f"G_prom = {G_prom:.1f}, G4={G4:.1f}, G5={G5:.1f}, G6={G6:.1f}, G7={G7:.1f}")
    print(f"G_vto={G_vto:.1f}, G_nto={G_nto:.1f}")
    print(f"P_prom = {P_prom:.3f} МПа")

    G_ots1 = max(1.0, G_in - G_prom)
    G_ots2 = max(1.0, G_ots1 - G4)
    G_ots3 = max(1.0, G_ots2 - G5)
    G_ots4 = max(1.0, G_ots3 - G6)
    G_ots5 = max(1.0, G_ots4 - G7)
    G_ots6 = max(1.0, G_ots5 - G_vto)
    G_ots7 = max(1.0, G_ots6 - G_nto)

    s4 = _scale(220.0, G_ots1)
    s5 = _scale(210.0, G_ots2)
    s6 = _scale(205.0, G_ots3)
    s7 = _scale(200.0, G_ots4)
    sv = _scale(190.0, G_ots5)
    sn = _scale(180.0, G_ots6)

    P4 = float(np.clip(0.658 * s4, 0.45, min(0.85, P_prom * 0.75)))
    P5 = float(np.clip(0.259 * s5, 0.18, min(0.38, P4 * 0.52)))
    P6 = float(np.clip(0.098 * s6, 0.07, min(0.16, P5 * 0.48)))
    P7 = float(np.clip(0.049 * s7, 0.035, min(0.08, P6 * 0.58)))

    P_vto = float(np.clip(0.120 * sv, max(0.09, P7 * 1.7), 0.20))
    P_nto = float(np.clip(0.090 * sn, max(0.07, P7 * 1.4), min(0.16, P_vto * 0.92)))

    # Предварительная оценка вакуума по хвостовому расходу.
    P_k = 0.0030 + 0.000010 * G_ots7
    P_k = float(np.clip(P_k, 0.0030, 0.0065))

    print(f"\nОтсек 1: промотбор -> IV отбор, расход {G_ots1:.2f} т/ч, P4 = {P4:.4f} МПа")
    print(f"Отсек 2: IV -> V, расход {G_ots2:.2f} т/ч, P5 = {P5:.4f} МПа")
    print(f"Отсек 3: V -> VI, расход {G_ots3:.2f} т/ч, P6 = {P6:.4f} МПа")
    print(f"Отсек 4: VI -> VII, расход {G_ots4:.2f} т/ч, P7 = {P7:.4f} МПа")
    print(f"Отсек 5: VII -> ВТО, расход {G_ots5:.2f} т/ч, P_vto = {P_vto:.4f} МПа")
    print(f"Отсек 6: ВТО -> НТО, расход {G_ots6:.2f} т/ч, P_nto = {P_nto:.4f} МПа")
    print(f"Отсек 7: НТО -> конденсатор, расход {G_ots7:.2f} т/ч, P_k(предв.) = {P_k:.4f} МПа")

    print(f"\n{'=' * 60}")
    print("ИТОГОВЫЕ ДАВЛЕНИЯ В ОТБОРАХ ЦСНД:")
    print(f"P4 (ПНД-4) = {P4:.4f} МПа")
    print(f"P5 (ПНД-3) = {P5:.4f} МПа")
    print(f"P6 (ПНД-2) = {P6:.4f} МПа")
    print(f"P7 (ПНД-1) = {P7:.4f} МПа")
    print(f"P_vto = {P_vto:.4f} МПа")
    print(f"P_nto = {P_nto:.4f} МПа")
    print(f"P_k = {P_k:.4f} МПа ({P_k * 1000:.1f} кПа)")
    print(f"G_k = {G_ots7:.2f} т/ч")

    return {
        'P4': P4,
        'P5': P5,
        'P6': P6,
        'P7': P7,
        'P_vto': P_vto,
        'P_nto': P_nto,
        'P_k': P_k,
        'G_k': G_ots7,
    }


def calc_power_csnd_full(h_prom, h4, h5, h6, h7, h_vto, h_nto, h_k,
                         G_in, G_prom, G4, G5, G6, G7, G_vto, G_nto,
                         eta_oi=None):
    """Расчёт мощности ЦСНД по отсекам с использованием действительных энтальпий."""
    if eta_oi is None:
        eta_oi = eta_oi_csnd_full

    kgs = 1000 / 3600
    G_in_kg = G_in * kgs
    G_prom_kg = G_prom * kgs
    G4_kg = G4 * kgs
    G5_kg = G5 * kgs
    G6_kg = G6 * kgs
    G7_kg = G7 * kgs
    G_vto_kg = G_vto * kgs
    G_nto_kg = G_nto * kgs

    print(f"\n{'=' * 60}")
    print("РАСЧЕТ МОЩНОСТИ ЦСНД")
    print(f"{'=' * 60}")

    G_ots1_kg = max(0.0, G_in_kg - G_prom_kg)
    delta_h1 = max(0.0, h_prom - h4)
    N1 = G_ots1_kg * delta_h1 * eta_oi[0] / 1000
    print(f"Отсек 1 (промотор-IV): G={G_ots1_kg*3600/1000:.1f} т/ч, Δh={delta_h1:.1f}, N={N1:.2f} МВт")

    G_ots2_kg = max(0.0, G_ots1_kg - G4_kg)
    delta_h2 = max(0.0, h4 - h5)
    N2 = G_ots2_kg * delta_h2 * eta_oi[1] / 1000
    print(f"Отсек 2 (IV-V): G={G_ots2_kg*3600/1000:.1f} т/ч, Δh={delta_h2:.1f}, N={N2:.2f} МВт")

    G_ots3_kg = max(0.0, G_ots2_kg - G5_kg)
    delta_h3 = max(0.0, h5 - h6)
    N3 = G_ots3_kg * delta_h3 * eta_oi[2] / 1000
    print(f"Отсек 3 (V-VI): G={G_ots3_kg*3600/1000:.1f} т/ч, Δh={delta_h3:.1f}, N={N3:.2f} МВт")

    G_ots4_kg = max(0.0, G_ots3_kg - G6_kg)
    delta_h4 = max(0.0, h6 - h7)
    N4 = G_ots4_kg * delta_h4 * eta_oi[3] / 1000
    print(f"Отсек 4 (VI-VII): G={G_ots4_kg*3600/1000:.1f} т/ч, Δh={delta_h4:.1f}, N={N4:.2f} МВт")

    G_ots5_kg = max(0.0, G_ots4_kg - G7_kg)
    delta_h5 = max(0.0, h7 - h_vto)
    N5 = G_ots5_kg * delta_h5 * eta_oi[4] / 1000
    print(f"Отсек 5 (VII-ВТО): G={G_ots5_kg*3600/1000:.1f} т/ч, Δh={delta_h5:.1f}, N={N5:.2f} МВт")

    G_ots6_kg = max(0.0, G_ots5_kg - G_vto_kg)
    delta_h6 = max(0.0, h_vto - h_nto)
    N6 = G_ots6_kg * delta_h6 * eta_oi[5] / 1000
    print(f"Отсек 6 (ВТО-НТО): G={G_ots6_kg*3600/1000:.1f} т/ч, Δh={delta_h6:.1f}, N={N6:.2f} МВт")

    G_ots7_kg = max(0.0, G_ots6_kg - G_nto_kg)
    delta_h7 = max(0.0, h_nto - h_k)
    N7 = G_ots7_kg * delta_h7 * eta_oi[6] / 1000
    print(f"Отсек 7 (НТО-К): G={G_ots7_kg*3600/1000:.1f} т/ч, Δh={delta_h7:.1f}, N={N7:.2f} МВт")

    N_total = N1 + N2 + N3 + N4 + N5 + N6 + N7
    print(f"\nСуммарная мощность ЦСНД: {N_total:.2f} МВт")
    return N_total


def calc_h_values_csnd(pressures, h_prom_in, x_start=0.98):
    """Расчёт энтальпий в отборах ЦСНД с учётом влажности."""
    print(f"\n{'=' * 60}")
    print("РАСЧЕТ ЭНТАЛЬПИЙ В ОТБОРАХ ЦСНД")
    print(f"{'=' * 60}")

    x4 = max(0.90, x_start - 0.02)
    x5 = max(0.87, x4 - 0.03)
    x6 = max(0.84, x5 - 0.03)
    x7 = max(0.81, x6 - 0.03)
    x_vto = max(0.78, x7 - 0.02)
    x_nto = max(0.74, x_vto - 0.03)
    x_k = max(0.70, x_nto - 0.04)

    def wet_h(p, x):
        return h_water(p) + x * (h_steam_sat(p) - h_water(p))

    h4 = wet_h(pressures['P4'], x4)
    h5 = wet_h(pressures['P5'], x5)
    h6 = wet_h(pressures['P6'], x6)
    h7 = wet_h(pressures['P7'], x7)
    h_vto = wet_h(pressures['P_vto'], x_vto)
    h_nto = wet_h(pressures['P_nto'], x_nto)
    h_k = wet_h(pressures['P_k'], x_k)

    print(f"P4={pressures['P4']:.3f} МПа, ts={ts(pressures['P4']):.1f}°C, x4={x4:.3f}, h4={h4:.1f}")
    print(f"P5={pressures['P5']:.3f} МПа, ts={ts(pressures['P5']):.1f}°C, x5={x5:.3f}, h5={h5:.1f}")
    print(f"P6={pressures['P6']:.3f} МПа, ts={ts(pressures['P6']):.1f}°C, x6={x6:.3f}, h6={h6:.1f}")
    print(f"P7={pressures['P7']:.3f} МПа, ts={ts(pressures['P7']):.1f}°C, x7={x7:.3f}, h7={h7:.1f}")
    print(f"P_vto={pressures['P_vto']:.3f} МПа, ts={ts(pressures['P_vto']):.1f}°C, x_vto={x_vto:.3f}, h_vto={h_vto:.1f}")
    print(f"P_nto={pressures['P_nto']:.3f} МПа, ts={ts(pressures['P_nto']):.1f}°C, x_nto={x_nto:.3f}, h_nto={h_nto:.1f}")
    print(f"P_k={pressures['P_k']:.3f} МПа, ts={ts(pressures['P_k']):.1f}°C, x_k={x_k:.3f}, h_k={h_k:.1f}")

    return {
        'h4': h4,
        'h5': h5,
        'h6': h6,
        'h7': h7,
        'h_vto': h_vto,
        'h_nto': h_nto,
        'h_k': h_k,
        'x4': x4,
        'x5': x5,
        'x6': x6,
        'x7': x7,
        'x_vto': x_vto,
        'x_nto': x_nto,
        'x_k': x_k,
        'h_prom': h_prom_in,
    }


if __name__ == "__main__":
    pressures = calc_pressures_csnd_full(200.0, 0.0, 8.0, 10.0, 12.0, 8.0, 0.0, 70.0, 1.3)
    enthalpies = calc_h_values_csnd(pressures, 2930.0)
    power = calc_power_csnd_full(
        2930.0,
        enthalpies['h4'], enthalpies['h5'], enthalpies['h6'], enthalpies['h7'],
        enthalpies['h_vto'], enthalpies['h_nto'], enthalpies['h_k'],
        200.0, 0.0, 8.0, 10.0, 12.0, 8.0, 0.0, 70.0,
    )
    print(pressures, power)
