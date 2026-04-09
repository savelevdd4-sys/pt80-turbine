def air_to_water_temp(t_air_c: float, delta_c: float = 6.0) -> float:
    return t_air_c + delta_c

def condenser_pressure_from_water_temp(t_water_c: float, nominal_kpa: float = 5.0) -> float:
    return nominal_kpa + (t_water_c - 20.0) * 0.59

def environmental_power_correction(base_power_mw: float, model_pk_kpa: float, env_pk_kpa: float, mw_per_kpa: float = 1.1) -> float:
    penalty = max(0.0, env_pk_kpa - model_pk_kpa) * mw_per_kpa
    return max(0.0, base_power_mw - penalty)
