# run_calc.py
from services.calc_service import run_mode_calculation

def main():
    # Здесь можно изменить параметры режима
    mode_data = {
        "mode_id": "CONSOLE",
        "Nz": 80.0,           # электрическая мощность, МВт
        "Gprom": 0.0,         # производственный отбор, т/ч
        "Qtf": 60.0,          # тепловая нагрузка, Гкал/ч
        "shema_tf": 1,        # схема теплофикации (1 или 2)
    }

    print("Запуск расчёта с параметрами:", mode_data)
    result = run_mode_calculation(mode_data)
    results = result["results"]

    print("\n=== РЕЗУЛЬТАТЫ РАСЧЁТА ===")
    print(f"G0 (расход свежего пара) = {results['G0']} т/ч")
    print(f"Pк = {results['P_k']*1000:.2f} кПа")
    print(f"Nэл (задано) = {results['Nz']} МВт, Nэл (рассчитано) = {results['N_el_calc']:.2f} МВт")
    print(f"Удельный расход тепла q_t = {results['q_t']} ккал/кВт·ч")
    print(f"КПД брутто = {results['eta_brut']}%")
    print("\nДавления в отборах (МПа):")
    print(f"P1 = {results['P1']}")
    print(f"P2 = {results['P2']}")
    print(f"P3 = {results['P3']}")
    print(f"Pпром = {results['P_prom']}")
    print(f"Pвто = {results['P_vto']}")
    print(f"Pнто = {results['P_nto']}")
    print("\nРасходы в отборы (т/ч):")
    print(f"G1 (ПВД-7) = {results['G1']}")
    print(f"G2 (ПВД-6) = {results['G2']}")
    print(f"G3 (ПВД-5) = {results['G3']}")
    print(f"G4 (ПНД-4) = {results['G4']}")
    print(f"G5 (ПНД-3) = {results['G5']}")
    print(f"G6 (ПНД-2) = {results['G6']}")
    print(f"G7 (ПНД-1) = {results['G7']}")
    print(f"Gд (пар на деаэратор) = {results['G_steam_d']}")
    print(f"Gвто = {results['G_vto']}")
    print(f"Gнто = {results['G_nto']}")
    print(f"Gк (в конденсатор) = {results['G_cond']}")
    print(f"\nНевязка баланса: {results['delta_balance']} т/ч")
    print(f"Количество итераций: {results['iterations']}")

if __name__ == "__main__":
    main()