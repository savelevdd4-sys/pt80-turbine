
"""
psg.py - Расчёт подогревателей сетевой воды (ПСВ)
Для турбины ПТ-80/100-130/13
"""

import numpy as np
from steam_properties import ts, h_water, h_steam_sat, p_sat  # добавили p_sat
from config import dt_ned_PSG, cw

def calc_psg(Q_tf, scheme, t_water_in=50.0, G_water=None):
    """
    Расчёт параметров ПСВ (подогревателей сетевой воды)
    
    Parameters:
    Q_tf : float - тепловая нагрузка на теплофикацию, Гкал/ч
    scheme : int - схема теплофикации (1 - одноступенчатая, 2 - двухступенчатая)
    t_water_in : float - температура сетевой воды на входе в первый ПСВ, °C (по умолчанию 50)
    G_water : float - расход сетевой воды, т/ч (если None, рассчитывается по тепловой нагрузке)
    
    Returns:
    dict - словарь с параметрами ПСВ
    """
    # Если тепловая нагрузка отсутствует или очень мала, возвращаем нулевые значения
    if Q_tf <= 1e-6:
        results = {
            'G_water_tph': 0.0,
            't_water_in_c': t_water_in,
        }
        if scheme == 1:
            results['psv1'] = {
                'G_steam_tph': 0.0,
                'P_steam_mpa': 0.0,
                't_sat_c': 0.0,
                't_water_in_c': t_water_in,
                't_water_out_c': t_water_in,
                'delta_t_c': 0.0,
            }
        else:  # scheme == 2
            results['psv_nto'] = {
                'G_steam_tph': 0.0,
                'P_steam_mpa': 0.0,
                't_sat_c': 0.0,
                't_water_in_c': t_water_in,
                't_water_out_c': t_water_in,
                'delta_t_c': 0.0,
            }
            results['psv_vto'] = {
                'G_steam_tph': 0.0,
                'P_steam_mpa': 0.0,
                't_sat_c': 0.0,
                't_water_in_c': t_water_in,
                't_water_out_c': t_water_in,
                'delta_t_c': 0.0,
            }
            results['t_water_final_c'] = t_water_in
            results['delta_t_total_c'] = 0.0
        return results

    # Перевод в МВт
    Q_tf_MW = Q_tf * 1.163  # 1 Гкал/ч = 1.163 МВт
    
    # Если расход воды не задан, принимаем типовой перепад температур
    if G_water is None:
        if scheme == 1:
            delta_t = 60  # одноступенчатый подогрев от 50 до 110, например
        else:
            delta_t = 40  # на каждую ступень
        G_water_kg_s = Q_tf_MW * 1000 / (cw * delta_t)
        G_water = G_water_kg_s * 3600 / 1000  # т/ч
    else:
        G_water_kg_s = G_water * 1000 / 3600
    
    # Защита от нулевого расхода воды (на всякий случай)
    if G_water_kg_s <= 1e-6:
        results = {
            'G_water_tph': G_water,
            't_water_in_c': t_water_in,
        }
        if scheme == 1:
            results['psv1'] = {
                'G_steam_tph': 0.0,
                'P_steam_mpa': 0.0,
                't_sat_c': 0.0,
                't_water_in_c': t_water_in,
                't_water_out_c': t_water_in,
                'delta_t_c': 0.0,
            }
        else:
            results['psv_nto'] = {
                'G_steam_tph': 0.0,
                'P_steam_mpa': 0.0,
                't_sat_c': 0.0,
                't_water_in_c': t_water_in,
                't_water_out_c': t_water_in,
                'delta_t_c': 0.0,
            }
            results['psv_vto'] = {
                'G_steam_tph': 0.0,
                'P_steam_mpa': 0.0,
                't_sat_c': 0.0,
                't_water_in_c': t_water_in,
                't_water_out_c': t_water_in,
                'delta_t_c': 0.0,
            }
            results['t_water_final_c'] = t_water_in
            results['delta_t_total_c'] = 0.0
        return results

    results = {}
    
    if scheme == 1:
        # Одноступенчатая схема – только нижний ПСВ
        t_out = t_water_in + Q_tf_MW * 1000 / (G_water_kg_s * cw)
        t_sat_needed = t_out + dt_ned_PSG
        P_psv = p_sat(t_sat_needed)
        
        h_steam = h_steam_sat(P_psv)
        h_cond = h_water(P_psv)
        
        G_steam_kg_s = Q_tf_MW * 1000 / (h_steam - h_cond)
        G_steam = G_steam_kg_s * 3600 / 1000
        
        results['psv1'] = {
            'G_steam_tph': G_steam,
            'P_steam_mpa': P_psv,
            't_sat_c': t_sat_needed,
            't_water_in_c': t_water_in,
            't_water_out_c': t_out,
            'delta_t_c': t_out - t_water_in,
        }
        
    else:  # scheme == 2
        Q_vto = Q_tf_MW * 0.6
        Q_nto = Q_tf_MW * 0.4
        
        # Нижний ПСВ (НТО)
        t_nto_out = t_water_in + Q_nto * 1000 / (G_water_kg_s * cw)
        t_sat_needed_nto = t_nto_out + dt_ned_PSG
        P_nto = p_sat(t_sat_needed_nto)
        h_steam_nto = h_steam_sat(P_nto)
        h_cond_nto = h_water(P_nto)
        G_steam_nto_kg_s = Q_nto * 1000 / (h_steam_nto - h_cond_nto)
        G_steam_nto = G_steam_nto_kg_s * 3600 / 1000
        
        results['psv_nto'] = {
            'G_steam_tph': G_steam_nto,
            'P_steam_mpa': P_nto,
            't_sat_c': t_sat_needed_nto,
            't_water_in_c': t_water_in,
            't_water_out_c': t_nto_out,
            'delta_t_c': t_nto_out - t_water_in,
        }
        
        # Верхний ПСВ (ВТО)
        t_vto_in = t_nto_out
        t_vto_out = t_vto_in + Q_vto * 1000 / (G_water_kg_s * cw)
        t_sat_needed_vto = t_vto_out + dt_ned_PSG
        P_vto = p_sat(t_sat_needed_vto)
        h_steam_vto = h_steam_sat(P_vto)
        h_cond_vto = h_water(P_vto)
        G_steam_vto_kg_s = Q_vto * 1000 / (h_steam_vto - h_cond_vto)
        G_steam_vto = G_steam_vto_kg_s * 3600 / 1000
        
        results['psv_vto'] = {
            'G_steam_tph': G_steam_vto,
            'P_steam_mpa': P_vto,
            't_sat_c': t_sat_needed_vto,
            't_water_in_c': t_vto_in,
            't_water_out_c': t_vto_out,
            'delta_t_c': t_vto_out - t_vto_in,
        }
        
        results['t_water_final_c'] = t_vto_out
        results['delta_t_total_c'] = t_vto_out - t_water_in
    
    results['G_water_tph'] = G_water
    results['t_water_in_c'] = t_water_in
    return results
