# regeneration.py
"""
regeneration.py - Расчет регенеративной системы турбины ПТ-80/100-130/13
Включает ПНД, деаэратор и ПВД с каскадным сливом дренажей.

Исправления:
- единые теплофизические свойства берутся из steam_properties;
- корректный материальный баланс деаэратора (без «рождения» лишней воды);
- каскад дренажей считается по физически корректному направлению:
  дренажи более высокого давления подогревают ступени более низкого давления.
- ПВД рассчитываются через энтальпии, а не через cw.
"""

from config import dt_ned_PND, dt_ned_PVD, Pd, t_vozvrat, cw
from steam_properties import ts, h_water, h_steam_sat, h_steam, h_water_temp


# ========== РАСЧЕТ ПНД С КАСКАДНЫМ СЛИВОМ ==========

def calc_pnd_cascade(pressures, G_ok, t_k):
    """
    Расчет подогревателей низкого давления с каскадным сливом дренажей.

    Порядок по воде: ПНД-1 -> ПНД-2 -> ПНД-3 -> ПНД-4.
    Порядок по дренажам: ПНД-4 -> ПНД-3 -> ПНД-2 -> ПНД-1.
    """
    print("\n" + "=" * 70)
    print("РАСЧЕТ ПНД С КАСКАДНЫМ СЛИВОМ ДРЕНАЖЕЙ")
    print("=" * 70)

    P4 = pressures.get('P4', 0.658)
    P5 = pressures.get('P5', 0.259)
    P6 = pressures.get('P6', 0.098)
    P7 = pressures.get('P7', 0.049)

    ts4 = ts(P4)
    ts5 = ts(P5)
    ts6 = ts(P6)
    ts7 = ts(P7)

    print("\n📊 ПАРАМЕТРЫ ГРЕЮЩЕГО ПАРА:")
    print(f"ПНД-4: P={P4:.4f} МПа, ts={ts4:.1f}°C")
    print(f"ПНД-3: P={P5:.4f} МПа, ts={ts5:.1f}°C")
    print(f"ПНД-2: P={P6:.4f} МПа, ts={ts6:.1f}°C")
    print(f"ПНД-1: P={P7:.4f} МПа, ts={ts7:.1f}°C")
    print(f"G_ok = {G_ok:.1f} т/ч, t_k = {t_k:.1f}°C")

    G_ok_kg_s = G_ok * 1000 / 3600

    # Температуры по тракту воды
    t_out1 = max(t_k, ts7 - dt_ned_PND)
    t_out2 = max(t_out1, ts6 - dt_ned_PND)
    t_out3 = max(t_out2, ts5 - dt_ned_PND)
    t_out4 = max(t_out3, ts4 - dt_ned_PND)

    q1 = G_ok_kg_s * cw * max(0.0, t_out1 - t_k)
    q2 = G_ok_kg_s * cw * max(0.0, t_out2 - t_out1)
    q3 = G_ok_kg_s * cw * max(0.0, t_out3 - t_out2)
    q4 = G_ok_kg_s * cw * max(0.0, t_out4 - t_out3)

    # Сначала самая высокая ступень, потом учитываем каскад дренажей вниз
    r4 = h_steam_sat(P4) - h_water(P4)
    G4 = q4 / r4 * 3600 / 1000 if q4 > 0 and r4 > 0 else 0.0

    q_drain_45 = (G4 * 1000 / 3600) * max(0.0, h_water(P4) - h_water(P5))
    r5 = h_steam_sat(P5) - h_water(P5)
    q5_need = max(0.0, q3 - q_drain_45)
    G5 = q5_need / r5 * 3600 / 1000 if q5_need > 0 and r5 > 0 else 0.0

    q_drain_56 = ((G4 + G5) * 1000 / 3600) * max(0.0, h_water(P5) - h_water(P6))
    r6 = h_steam_sat(P6) - h_water(P6)
    q6_need = max(0.0, q2 - q_drain_56)
    G6 = q6_need / r6 * 3600 / 1000 if q6_need > 0 and r6 > 0 else 0.0

    q_drain_67 = ((G4 + G5 + G6) * 1000 / 3600) * max(0.0, h_water(P6) - h_water(P7))
    r7 = h_steam_sat(P7) - h_water(P7)
    q7_need = max(0.0, q1 - q_drain_67)
    G7 = q7_need / r7 * 3600 / 1000 if q7_need > 0 and r7 > 0 else 0.0

    print("\n📊 ТЕПЛОВЫЕ НАГРУЗКИ ПО ТРАКТУ ВОДЫ:")
    print(f"ПНД-1: {t_k:.1f} → {t_out1:.1f} °C, Q1 = {q1:.1f} кВт")
    print(f"ПНД-2: {t_out1:.1f} → {t_out2:.1f} °C, Q2 = {q2:.1f} кВт")
    print(f"ПНД-3: {t_out2:.1f} → {t_out3:.1f} °C, Q3 = {q3:.1f} кВт")
    print(f"ПНД-4: {t_out3:.1f} → {t_out4:.1f} °C, Q4 = {q4:.1f} кВт")

    print("\n📊 ВКЛАД КАСКАДА ДРЕНАЖЕЙ:")
    print(f"ПНД-3 получает от дренажа ПНД-4: {q_drain_45:.1f} кВт")
    print(f"ПНД-2 получает от дренажей ПНД-4/3: {q_drain_56:.1f} кВт")
    print(f"ПНД-1 получает от дренажей ПНД-4/3/2: {q_drain_67:.1f} кВт")

    print(f"\n{'=' * 70}")
    print("РЕЗУЛЬТАТЫ РАСЧЕТА ПНД")
    print(f"{'=' * 70}")
    print(f"G4 (ПНД-4) = {G4:.2f} т/ч")
    print(f"G5 (ПНД-3) = {G5:.2f} т/ч")
    print(f"G6 (ПНД-2) = {G6:.2f} т/ч")
    print(f"G7 (ПНД-1) = {G7:.2f} т/ч")
    print(f"t_ok после ПНД-4 = {t_out4:.1f}°C")

    return {
        'G4': G4,
        'G5': G5,
        'G6': G6,
        'G7': G7,
        't_ok': t_out4,
    }


# ========== РАСЧЕТ ДЕАЭРАТОРА ==========

def calc_deaerator(G_ok, t_ok, G_drain_pvd5, t_drain_pvd5, G_return, t_return):
    """Расчет деаэратора питательной воды (0.6 МПа)."""
    print("\n" + "=" * 70)
    print("РАСЧЕТ ДЕАЭРАТОРА ПИТАТЕЛЬНОЙ ВОДЫ")
    print("=" * 70)
    print(f"G_ok = {G_ok:.1f} т/ч, t_ok = {t_ok:.1f}°C")
    print(f"G_drain_pvd5 = {G_drain_pvd5:.1f} т/ч, t_drain = {t_drain_pvd5:.1f}°C")
    print(f"G_return = {G_return:.1f} т/ч, t_return = {t_return:.1f}°C")

    P_d = Pd
    ts_d_val = ts(P_d)
    h_sat_liq = h_water(P_d)
    h_sat_vap = h_steam_sat(P_d)

    print("\n📌 Параметры деаэратора:")
    print(f"  P_d = {P_d} МПа")
    print(f"  ts_d = {ts_d_val:.1f}°C")
    print(f"  h' = {h_sat_liq:.1f} кДж/кг")
    print(f"  h'' = {h_sat_vap:.1f} кДж/кг")

    h_ok = h_water_temp(t_ok)
    h_drain = h_water_temp(t_drain_pvd5) if G_drain_pvd5 > 0 else 0.0
    h_return = h_water_temp(t_return) if G_return > 0 else 0.0

    print("\n📊 Энтальпии потоков, кДж/кг:")
    print(f"  h_ok = {h_ok:.1f}")
    print(f"  h_drain = {h_drain:.1f}")
    print(f"  h_return = {h_return:.1f}")
    print(f"  h_pv (целевая) = {h_sat_liq:.1f}")
    print(f"  h_steam_d = {h_sat_vap:.1f}")

    G_ok_kg_s = G_ok * 1000 / 3600
    G_drain_kg_s = G_drain_pvd5 * 1000 / 3600
    G_return_kg_s = G_return * 1000 / 3600

    # Корректный материальный баланс: масса воды на входе фиксирована.
    G_liq_in_kg_s = G_ok_kg_s + G_drain_kg_s + G_return_kg_s
    Q_in = G_ok_kg_s * h_ok + G_drain_kg_s * h_drain + G_return_kg_s * h_return
    Q_out_needed = G_liq_in_kg_s * h_sat_liq

    print("\n📊 Тепловой баланс:")
    print(f"  Q_in = {Q_in / 1000:.2f} МВт")
    print(f"  Q_out_needed = {Q_out_needed / 1000:.2f} МВт")

    if Q_in >= Q_out_needed:
        print("  ✅ Тепла входных потоков достаточно")
        G_steam_d_kg_s = 0.0
    else:
        Q_steam_needed = Q_out_needed - Q_in
        denom = max(1e-6, h_sat_vap - h_sat_liq)
        G_steam_d_kg_s = Q_steam_needed / denom
        print(f"  Требуется греющего пара: {G_steam_d_kg_s:.3f} кг/с")

    G_pv_kg_s = G_liq_in_kg_s + G_steam_d_kg_s
    G_pv = G_pv_kg_s * 3600 / 1000
    G_steam_d = G_steam_d_kg_s * 3600 / 1000
    t_pv = ts_d_val

    print(f"\n{'=' * 70}")
    print("РЕЗУЛЬТАТЫ РАСЧЕТА ДЕАЭРАТОРА")
    print(f"{'=' * 70}")
    print(f"G_steam_d = {G_steam_d:.2f} т/ч - расход греющего пара")
    print(f"G_pv = {G_pv:.2f} т/ч - расход питательной воды")
    print(f"t_pv = {t_pv:.1f}°C - температура питательной воды")

    return {
        'G_pv': G_pv,
        'G_steam_d': G_steam_d,
        't_pv': t_pv,
    }


# ========== РАСЧЕТ ПВД С КАСКАДНЫМ СЛИВОМ (ПРАВИЛЬНАЯ ВЕРСИЯ) ==========

def calc_pvd_cascade(pressures_cvd, G_pv_in, t_pv_in):
    """
    Расчёт каскада ПВД (ПВД-7, ПВД-6, ПВД-5) через энтальпии.
    
    Parameters:
    pressures_cvd : dict – давления в отборах (P1, P2, P3) в МПа
    G_pv_in : float – расход питательной воды на входе в ПВД-5, т/ч
    t_pv_in : float – температура воды на входе в ПВД-5 (после деаэратора), °C
    
    Returns:
    dict – расходы пара G1, G2, G3, температура после ПВД-7 (t_pv) и температура дренажа из ПВД-5 (t_drain_pvd5)
    """
    from steam_properties import ts, h_steam_sat, h_water, h_water_temp
    from config import dt_ned_PVD

    P1 = pressures_cvd['P1']
    P2 = pressures_cvd['P2']
    P3 = pressures_cvd['P3']

    # Температуры насыщения в отборах
    ts1 = ts(P1)
    ts2 = ts(P2)
    ts3 = ts(P3)

    # Энтальпии греющего пара (сухой насыщенный пар)
    h1 = h_steam_sat(P1)
    h2 = h_steam_sat(P2)
    h3 = h_steam_sat(P3)

    # Энтальпии конденсата при температурах насыщения
    h_k1 = h_water(P1)
    h_k2 = h_water(P2)
    h_k3 = h_water(P3)

    # Температуры воды после каждого ПВД (с учётом недогрева)
    t_out5 = ts3 - dt_ned_PVD
    t_out6 = ts2 - dt_ned_PVD
    t_out7 = ts1 - dt_ned_PVD

    # Энтальпии воды в соответствующих точках
    h_in5 = h_water_temp(t_pv_in)
    h_out5 = h_water_temp(t_out5)
    h_in6 = h_out5
    h_out6 = h_water_temp(t_out6)
    h_in7 = h_out6
    h_out7 = h_water_temp(t_out7)

    # Расход воды в кг/с
    G_pv_kg_s = G_pv_in * 1000 / 3600

    # Тепловые нагрузки подогревателей (кВт)
    Q5 = G_pv_kg_s * (h_out5 - h_in5)
    Q6 = G_pv_kg_s * (h_out6 - h_in6)
    Q7 = G_pv_kg_s * (h_out7 - h_in7)

    # ПВД-7
    G1_kg_s = Q7 / (h1 - h_k1) if (h1 - h_k1) > 0 else 0
    G1 = G1_kg_s * 3600 / 1000

    # ПВД-6: учитываем тепло от дренажа ПВД-7
    Q_drain_7 = G1_kg_s * (h_k1 - h_k2)
    Q6_need = Q6 - Q_drain_7
    if Q6_need < 0:
        G2_kg_s = 0
    else:
        G2_kg_s = Q6_need / (h2 - h_k2) if (h2 - h_k2) > 0 else 0
    G2 = G2_kg_s * 3600 / 1000

    # ПВД-5: учитываем тепло от дренажей ПВД-7 и ПВД-6
    Q_drain_6 = (G1_kg_s + G2_kg_s) * (h_k2 - h_k3)
    Q5_need = Q5 - Q_drain_6
    if Q5_need < 0:
        G3_kg_s = 0
    else:
        G3_kg_s = Q5_need / (h3 - h_k3) if (h3 - h_k3) > 0 else 0
    G3 = G3_kg_s * 3600 / 1000

    # Итоговая температура питательной воды (после ПВД-7)
    t_pv_final = t_out7
    # Температура дренажа из ПВД-5 (для деаэратора)
    t_drain_pvd5 = t_out5

    print("\n" + "=" * 70)
    print("РАСЧЕТ ПВД С КАСКАДНЫМ СЛИВОМ ДРЕНАЖЕЙ")
    print("=" * 70)
    print("\n📊 ДАВЛЕНИЯ И ТЕМПЕРАТУРЫ НАСЫЩЕНИЯ:")
    print(f"ПВД-7: P={P1:.3f} МПа, ts={ts1:.1f}°C")
    print(f"ПВД-6: P={P2:.3f} МПа, ts={ts2:.1f}°C")
    print(f"ПВД-5: P={P3:.3f} МПа, ts={ts3:.1f}°C")
    print(f"G_pv = {G_pv_in:.1f} т/ч, t_вх из деаэратора = {t_pv_in:.1f}°C")

    print("\n📊 ТЕПЛОВЫЕ НАГРУЗКИ ПО ТРАКТУ ПИТАТЕЛЬНОЙ ВОДЫ:")
    print(f"ПВД-5: {t_pv_in:.1f} → {t_out5:.1f} °C, Q5 = {Q5/1000:.2f} МВт")
    print(f"ПВД-6: {t_out5:.1f} → {t_out6:.1f} °C, Q6 = {Q6/1000:.2f} МВт")
    print(f"ПВД-7: {t_out6:.1f} → {t_out7:.1f} °C, Q7 = {Q7/1000:.2f} МВт")

    print("\n📊 ВКЛАД КАСКАДА ДРЕНАЖЕЙ:")
    print(f"ПВД-6 получает от дренажа ПВД-7: {Q_drain_7/1000:.2f} МВт")
    print(f"ПВД-5 получает от дренажей ПВД-7/6: {Q_drain_6/1000:.2f} МВт")

    print(f"\n{'=' * 70}")
    print("РЕЗУЛЬТАТЫ РАСЧЕТА ПВД")
    print(f"{'=' * 70}")
    print(f"G1 (ПВД-7) = {G1:.2f} т/ч")
    print(f"G2 (ПВД-6) = {G2:.2f} т/ч")
    print(f"G3 (ПВД-5) = {G3:.2f} т/ч")
    print(f"t_пв (после ПВД-7) = {t_pv_final:.1f}°C")
    print(f"t_дренажа ПВД-5 = {t_drain_pvd5:.1f}°C")

    return {
        'G1': round(G1, 2),
        'G2': round(G2, 2),
        'G3': round(G3, 2),
        't_pv': round(t_pv_final, 1),      # температура питательной воды после ПВД-7
        't_drain_pvd5': round(t_drain_pvd5, 1),  # температура дренажа из ПВД-5
    }


# ========== ПОЛНЫЙ РАСЧЕТ РЕГЕНЕРАЦИИ ==========

def calc_regeneration_full(pressures_cvd, pressures_csnd, enthalpies_csnd, G_ok, t_k, G_return, t_return):
    """Полный расчет регенеративной системы турбоустановки."""
    print("\n" + "=" * 80)
    print("ПОЛНЫЙ РАСЧЕТ РЕГЕНЕРАТИВНОЙ СИСТЕМЫ")
    print("=" * 80)

    pnd_results = calc_pnd_cascade(pressures_csnd, G_ok, t_k)

    deaerator_results_1 = calc_deaerator(
        G_ok,
        pnd_results['t_ok'],
        0,
        0,
        G_return,
        t_return,
    )

    print("\n📌 ПОСЛЕ ДЕАЭРАТОРА (первое приближение):")
    print(f"G_pv = {deaerator_results_1['G_pv']:.2f} т/ч")
    print(f"t_pv = {deaerator_results_1['t_pv']:.1f}°C")

    pvd_results = calc_pvd_cascade(pressures_cvd, deaerator_results_1['G_pv'], deaerator_results_1['t_pv'])

    deaerator_results_final = calc_deaerator(
        G_ok,
        pnd_results['t_ok'],
        pvd_results['G3'],
        pvd_results['t_drain_pvd5'],  # используем температуру дренажа ПВД-5
        G_return,
        t_return,
    )

    print("\n📌 ПОСЛЕ ДЕАЭРАТОРА (уточненный):")
    print(f"G_pv = {deaerator_results_final['G_pv']:.2f} т/ч")
    print(f"G_steam_d = {deaerator_results_final['G_steam_d']:.2f} т/ч")

    pvd_results_final = calc_pvd_cascade(
        pressures_cvd,
        deaerator_results_final['G_pv'],
        deaerator_results_final['t_pv'],
    )

    results = {
        'G1': pvd_results_final['G1'],
        'G2': pvd_results_final['G2'],
        'G3': pvd_results_final['G3'],
        'G4': pnd_results['G4'],
        'G5': pnd_results['G5'],
        'G6': pnd_results['G6'],
        'G7': pnd_results['G7'],
        'G_steam_d': deaerator_results_final['G_steam_d'],
        't_pv': pvd_results_final['t_pv'],      # температура после ПВД-7
        't_ok': pnd_results['t_ok'],
        'G_pv': deaerator_results_final['G_pv'],
    }

    print("\n" + "=" * 80)
    print("ИТОГОВЫЕ ПАРАМЕТРЫ РЕГЕНЕРАЦИИ")
    print("=" * 80)
    print(f"t_ok = {pnd_results['t_ok']:.1f}°C")
    print(f"t_pv = {pvd_results_final['t_pv']:.1f}°C")
    print(f"G_pv = {deaerator_results_final['G_pv']:.2f} т/ч")
    print(f"G_steam_d = {deaerator_results_final['G_steam_d']:.2f} т/ч")
    print("\nРАСХОДЫ В ОТБОРЫ (т/ч):")
    print(f"  ПВД-7 (G1): {pvd_results_final['G1']:.2f}")
    print(f"  ПВД-6 (G2): {pvd_results_final['G2']:.2f}")
    print(f"  ПВД-5 (G3): {pvd_results_final['G3']:.2f}")
    print(f"  ПНД-4 (G4): {pnd_results['G4']:.2f}")
    print(f"  ПНД-3 (G5): {pnd_results['G5']:.2f}")
    print(f"  ПНД-2 (G6): {pnd_results['G6']:.2f}")
    print(f"  ПНД-1 (G7): {pnd_results['G7']:.2f}")

    return results


if __name__ == "__main__":
    pressures_cvd = {'P1': 4.12, 'P2': 2.72, 'P3': 1.30, 'P_prom': 1.30}
    pressures_csnd = {'P4': 0.658, 'P5': 0.259, 'P6': 0.098, 'P7': 0.049, 'P_vto': 0.12, 'P_nto': 0.09, 'P_k': 0.0045}
    enthalpies_csnd = {'h4': 2650, 'h5': 2550, 'h6': 2450, 'h7': 2350, 'h_vto': 2700, 'h_nto': 2600, 'h_k': 2300}
    test = calc_regeneration_full(pressures_cvd, pressures_csnd, enthalpies_csnd, 250.0, 35.0, 50.0, t_vozvrat)
    print(test)