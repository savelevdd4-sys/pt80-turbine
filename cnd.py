"""
cnd.py - Расчет конденсатора турбины ПТ-80/100-130/13
Основано на тепловом балансе и корректной зависимости P = f(tsat)
С улучшенной зависимостью K от расхода пара
"""

import numpy as np
import math
from config import Fk, cw, W_nom, tw1_nom, Pk_nom

def ts(P):
    """
    Температура насыщения от давления (корректная аппроксимация)
    P - давление в МПа
    возвращает температуру в °C
    """
    if P < 0.1:
        # Для вакуума (конденсатор) - точная аппроксимация по таблицам
        if P <= 0.002:
            return 6.5 + 5500 * P
        elif P <= 0.003:
            return 17.5 + 6600 * (P - 0.002)
        elif P <= 0.004:
            return 24.1 + 4400 * (P - 0.003)
        elif P <= 0.005:
            return 28.5 + 4400 * (P - 0.004)
        elif P <= 0.006:
            return 32.9 + 3300 * (P - 0.005)
        elif P <= 0.007:
            return 36.2 + 2800 * (P - 0.006)
        elif P <= 0.008:
            return 39.0 + 2500 * (P - 0.007)
        elif P <= 0.009:
            return 41.5 + 2300 * (P - 0.008)
        elif P <= 0.010:
            return 43.8 + 2000 * (P - 0.009)
        elif P <= 0.015:
            return 45.8 + 1640 * (P - 0.010)
        elif P <= 0.020:
            return 54.0 + 1220 * (P - 0.015)
        elif P <= 0.025:
            return 60.1 + 900 * (P - 0.020)
        elif P <= 0.030:
            return 64.6 + 900 * (P - 0.025)
        elif P <= 0.035:
            return 69.1 + 720 * (P - 0.030)
        elif P <= 0.040:
            return 72.7 + 640 * (P - 0.035)
        elif P <= 0.045:
            return 75.9 + 560 * (P - 0.040)
        elif P <= 0.050:
            return 78.7 + 520 * (P - 0.045)
        elif P <= 0.055:
            return 81.3 + 480 * (P - 0.050)
        elif P <= 0.060:
            return 83.7 + 440 * (P - 0.055)
        elif P <= 0.065:
            return 85.9 + 420 * (P - 0.060)
        elif P <= 0.070:
            return 88.0 + 380 * (P - 0.065)
        elif P <= 0.075:
            return 89.9 + 380 * (P - 0.070)
        elif P <= 0.080:
            return 91.8 + 340 * (P - 0.075)
        elif P <= 0.085:
            return 93.5 + 340 * (P - 0.080)
        elif P <= 0.090:
            return 95.2 + 300 * (P - 0.085)
        elif P <= 0.095:
            return 96.7 + 300 * (P - 0.090)
        elif P <= 0.100:
            return 98.2 + 280 * (P - 0.095)
        else:
            return 99.6 + 236 * (P - 0.10)
    else:
        # Для высоких давлений
        return 42.6776 * math.log(P) + 93.6543

def h_water(P):
    """Энтальпия кипящей воды, кДж/кг"""
    return 4.19 * ts(P)

def h_steam_sat(P):
    """Энтальпия сухого насыщенного пара, кДж/кг"""
    return 2500 + 1.88 * ts(P)

def h_wet_steam(P, x):
    """Энтальпия влажного пара, кДж/кг"""
    return h_water(P) + x * (h_steam_sat(P) - h_water(P))

def calc_condenser(G_k, h_k, W, tw1):
    """
    Расчет давления в конденсаторе с улучшенной зависимостью K от расхода
    
    Parameters:
    G_k : float - расход пара в конденсатор, т/ч
    h_k : float - энтальпия пара на входе в конденсатор, кДж/кг
    W : float - расход охлаждающей воды, м³/ч
    tw1 : float - температура охлаждающей воды на входе, °C
    
    Returns:
    dict - P_k (МПа), tsat (°C), tw2 (°C), Q_k (МВт)
    """
    print(f"\n{'='*60}")
    print("РАСЧЕТ КОНДЕНСАТОРА (с улучшенной моделью)")
    print(f"{'='*60}")
    print(f"G_k = {G_k:.1f} т/ч, h_k = {h_k:.1f} кДж/кг")
    print(f"W = {W:.0f} м³/ч, tw1 = {tw1:.1f}°C")
    print(f"Fk = {Fk} м² - поверхность охлаждения")
    
    # Перевод в кг/с
    G_k_kg_s = G_k * 1000 / 3600
    W_kg_s = W * 1000 / 3600
    
    # Начальное приближение - номинальное давление
    P_k = Pk_nom  # 0.005 МПа
    
    # Номинальный расход пара в конденсатор (для 80 МВт)
    G_k_nom = 220.0  # т/ч
    
    # Базовый коэффициент теплопередачи
    K_base = 4.2  # кВт/(м²·°C)
    
    print(f"\n📊 ИТЕРАЦИОННЫЙ РАСЧЕТ:")
    print("-" * 70)
    print(f"  Номинальный расход: Gк_ном = {G_k_nom:.1f} т/ч")
    print(f"  Базовый K: {K_base:.2f} кВт/(м²·°C)")
    print("-" * 70)
    
    for iteration in range(20):
        # Температура насыщения при текущем давлении
        tsat = ts(P_k)
        
        # Энтальпия конденсата (вода на линии насыщения)
        h_k_cond = h_water(P_k)
        
        # Тепловая нагрузка конденсатора
        Q_k = G_k_kg_s * (h_k - h_k_cond)  # кВт
        Q_k_MW = Q_k / 1000  # МВт
        
        # Нагрев охлаждающей воды
        dt_w = Q_k / (W_kg_s * cw)  # °C
        tw2 = tw1 + dt_w
        
        # Средняя температура охлаждающей воды
        tw_avg = (tw1 + tw2) / 2
        
        # === УЛУЧШЕННАЯ МОДЕЛЬ КОЭФФИЦИЕНТА ТЕПЛОПЕРЕДАЧИ ===
        
        # 1. Базовая коррекция по расходу (главный фактор)
        # При увеличении расхода пара K растет из-за турбулизации потока
        G_k_ratio = G_k / G_k_nom
        K_factor_flow = 0.8 + 0.4 * G_k_ratio - 0.05 * G_k_ratio**2
        # При G_k = G_k_nom: 0.8 + 0.4 - 0.05 = 1.15
        # При G_k = 0.5*G_k_nom: 0.8 + 0.2 - 0.0125 = 0.9875
        # При G_k = 1.5*G_k_nom: 0.8 + 0.6 - 0.1125 = 1.2875
        
        # 2. Коррекция по средней температуре
        # При повышении температуры K немного снижается
        K_factor_temp = 1.0 - 0.005 * (tw_avg - 20)
        K_factor_temp = max(0.9, min(1.05, K_factor_temp))
        
        # 3. Коррекция по температурному напору
        # При большом напоре K выше
        delta_t = tsat - tw_avg
        K_factor_dt = 1.0 + 0.02 * (delta_t - 10) / 10
        K_factor_dt = max(0.95, min(1.1, K_factor_dt))
        
        # Итоговый коэффициент теплопередачи
        K = K_base * K_factor_flow * K_factor_temp * K_factor_dt
        
        # Ограничиваем разумными пределами
        K = max(2.5, min(6.0, K))
        
        # Требуемый температурный напор
        delta_t_needed = Q_k / (K * Fk)  # °C
        
        # Требуемая температура насыщения
        tsat_needed = tw_avg + delta_t_needed
        
        # Корректное определение давления по температуре насыщения
        if tsat_needed <= 24.1:
            P_k_new = 0.003
        elif tsat_needed <= 28.5:
            P_k_new = 0.003 + 0.001 * (tsat_needed - 24.1) / (28.5 - 24.1)
        elif tsat_needed <= 32.9:
            P_k_new = 0.004 + 0.001 * (tsat_needed - 28.5) / (32.9 - 28.5)
        elif tsat_needed <= 36.2:
            P_k_new = 0.005 + 0.001 * (tsat_needed - 32.9) / (36.2 - 32.9)
        elif tsat_needed <= 39.0:
            P_k_new = 0.006 + 0.001 * (tsat_needed - 36.2) / (39.0 - 36.2)
        elif tsat_needed <= 41.5:
            P_k_new = 0.007 + 0.001 * (tsat_needed - 39.0) / (41.5 - 39.0)
        elif tsat_needed <= 43.8:
            P_k_new = 0.008 + 0.001 * (tsat_needed - 41.5) / (43.8 - 41.5)
        elif tsat_needed <= 45.8:
            P_k_new = 0.009 + 0.001 * (tsat_needed - 43.8) / (45.8 - 43.8)
        elif tsat_needed <= 54.0:
            P_k_new = 0.010 + 0.005 * (tsat_needed - 45.8) / (54.0 - 45.8)
        elif tsat_needed <= 60.1:
            P_k_new = 0.015 + 0.005 * (tsat_needed - 54.0) / (60.1 - 54.0)
        else:
            P_k_new = 0.020 + 0.010 * (tsat_needed - 60.1) / (69.1 - 60.1)
        
        P_k_new = max(0.002, min(0.020, P_k_new))
        
        # Относительное изменение
        delta_P = abs(P_k_new - P_k) / P_k if P_k > 0 else 1.0
        
        # Вывод через каждые 2 итерации для наглядности
        if iteration % 2 == 0 or delta_P < 0.01:
            print(f"  Итер {iteration+1:2d}: P_k={P_k:.4f} МПа ({P_k*1000:.1f} кПа), "
                  f"tsat={tsat:.2f}°C, tw2={tw2:.2f}°C, "
                  f"K={K:.2f} (flow={K_factor_flow:.2f}, temp={K_factor_temp:.2f}, dt={K_factor_dt:.2f})")
        
        if delta_P < 0.01:
            print(f"  ✅ Сходимость достигнута на итерации {iteration+1}")
            P_k = P_k_new
            break
        else:
            # Демпфирование для устойчивости
            P_k = 0.6 * P_k + 0.4 * P_k_new
    
    # Финальный расчет с установленным P_k
    tsat = ts(P_k)
    h_k_cond = h_water(P_k)
    Q_k = G_k_kg_s * (h_k - h_k_cond) / 1000  # МВт
    dt_w = Q_k * 1000 / (W_kg_s * cw)
    tw2 = tw1 + dt_w
    
    print(f"\n{'='*60}")
    print("ИТОГОВЫЕ ПАРАМЕТРЫ КОНДЕНСАТОРА")
    print(f"{'='*60}")
    print(f"  P_k = {P_k:.4f} МПа ({P_k*1000:.1f} кПа)")
    print(f"  tsat = {tsat:.1f} °C")
    print(f"  tw2 = {tw2:.1f} °C")
    print(f"  Нагрев воды = {tw2 - tw1:.1f} °C")
    print(f"  Тепловая нагрузка Q_k = {Q_k:.2f} МВт")
    
    # Оценка качества вакуума
    if P_k * 1000 < 4.0:
        print(f"  ✅ Отличный вакуум (< 4.0 кПа)")
    elif P_k * 1000 < 5.0:
        print(f"  ✅ Хороший вакуум (4.0-5.0 кПа)")
    elif P_k * 1000 < 6.0:
        print(f"  ⚠️ Удовлетворительный вакуум (5.0-6.0 кПа)")
    elif P_k * 1000 < 8.0:
        print(f"  ⚠️ Пониженный вакуум (6.0-8.0 кПа)")
    else:
        print(f"  ❌ Плохой вакуум (> 8.0 кПа)")
    
    return {
        'P_k': P_k,
        'tsat': tsat,
        'tw2': tw2,
        'Q_k': Q_k,
        'dt_w': dt_w
    }

def calc_condenser_nominal():
    """Расчет конденсатора для номинального режима"""
    print(f"\n{'='*60}")
    print("РАСЧЕТ КОНДЕНСАТОРА - НОМИНАЛЬНЫЙ РЕЖИМ")
    print(f"{'='*60}")
    
    G_k_nom = 220.0  # т/ч
    h_k_nom = 2350.0  # кДж/кг
    
    return calc_condenser(G_k_nom, h_k_nom, W_nom, tw1_nom)

def test_condenser_modes():
    """Тестирование конденсатора на разных режимах"""
    print("\n" + "="*80)
    print("ТЕСТИРОВАНИЕ КОНДЕНСАТОРА НА РАЗНЫХ РЕЖИМАХ")
    print("="*80)
    
    test_modes = [
        {"name": "80 МВт конденсационный", "G_k": 237.0, "h_k": 2326.4},
        {"name": "80 МВт теплофикационный", "G_k": 166.6, "h_k": 2326.4},
        {"name": "100 МВт конденсационный", "G_k": 290.1, "h_k": 2326.4},
    ]
    
    results = []
    for mode in test_modes:
        print(f"\n{'-'*60}")
        print(f"Режим: {mode['name']}")
        print(f"{'-'*60}")
        res = calc_condenser(mode['G_k'], mode['h_k'], W_nom, tw1_nom)
        results.append({
            'mode': mode['name'],
            'G_k': mode['G_k'],
            'P_k': res['P_k'] * 1000
        })
    
    print("\n" + "="*60)
    print("СВОДКА РЕЗУЛЬТАТОВ")
    print("="*60)
    print(f"{'Режим':<30} {'Gк, т/ч':<10} {'Pк, кПа':<10}")
    print("-" * 50)
    for r in results:
        print(f"{r['mode']:<30} {r['G_k']:<10.1f} {r['P_k']:<10.1f}")
    
    return results

if __name__ == "__main__":
    # Тестирование
    results = test_condenser_modes()