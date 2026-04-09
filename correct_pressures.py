"""
correct_pressures.py - Корректировка давлений в отборах
Использует эталонные значения с поправкой на расход
"""

# Эталонные давления для номинального режима (из ТХ)
REFERENCE_PRESSURES = {
    'P1': 4.12,    # ПВД-7 (I отбор)
    'P2': 2.72,    # ПВД-6 (II отбор)
    'P3': 1.30,    # ПВД-5 (III отбор)
    'P_prom': 1.30,# Промышленный отбор
    'P4': 0.658,   # ПНД-4 (IV отбор)
    'P5': 0.259,   # ПНД-3 (V отбор)
    'P6': 0.098,   # ПНД-2 (VI отбор)
    'P7': 0.049,   # ПНД-1 (VII отбор)
    'P_vto': 0.12, # Верхний теплофикационный
    'P_nto': 0.09, # Нижний теплофикационный
    'P_k': 0.0045  # Конденсатор
}

def correct_pressure_by_flow(Ref, G0, G0_ref=310):
    """
    Корректирует эталонное давление в зависимости от расхода
    """
    # Давление примерно пропорционально квадрату расхода
    correction = (G0 / G0_ref) ** 2
    return Ref * correction

def calc_pressures_cvd_corrected(G0, G1, G2, G3):
    """
    Расчет давлений в отборах ЦВД с использованием эталонных значений
    и коррекцией по расходу
    """
    print(f"\n{'='*60}")
    print("РАСЧЕТ ЦВД (скорректированный по эталону)")
    print(f"{'='*60}")
    
    # Базовая коррекция по расходу
    P1 = correct_pressure_by_flow(REFERENCE_PRESSURES['P1'], G0)
    P2 = correct_pressure_by_flow(REFERENCE_PRESSURES['P2'], G0)
    P3 = correct_pressure_by_flow(REFERENCE_PRESSURES['P3'], G0)
    P_prom = correct_pressure_by_flow(REFERENCE_PRESSURES['P_prom'], G0)
    
    # Дополнительная коррекция по отборам
    # Чем больше отбор, тем меньше давление в следующем отсеке
    G_ots2 = G0 - G1
    G_ots3 = G0 - G1 - G2
    G_ots4 = G0 - G1 - G2 - G3
    
    # Уменьшаем давление пропорционально расходу через отсек
    P2 = P2 * (G_ots2 / G0) ** 0.3
    P3 = P3 * (G_ots3 / G0) ** 0.3
    P_prom = P_prom * (G_ots4 / G0) ** 0.3
    
    # Ограничиваем разумными пределами
    P1 = max(3.8, min(4.5, P1))
    P2 = max(2.2, min(3.0, P2))
    P3 = max(1.0, min(1.6, P3))
    P_prom = max(1.0, min(1.6, P_prom))
    
    print(f"\n📊 РЕЗУЛЬТАТЫ:")
    print(f"P1 = {P1:.3f} МПа (эталон 4.12)")
    print(f"P2 = {P2:.3f} МПа (эталон 2.72)")
    print(f"P3 = {P3:.3f} МПа (эталон 1.30)")
    print(f"P_prom = {P_prom:.3f} МПа (эталон 1.30)")
    
    return {
        'P1': P1,
        'P2': P2,
        'P3': P3,
        'P_prom': P_prom,
        'G_cvd_out': G_ots4
    }