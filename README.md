# Лабораторна робота №3 — Моделювання системи управління енергопотоками EMS

**Варіант:** 3 — Лабораторія, СЕС 60 кВт, батарея 50 кВт·год, 3-зонний тариф  
**Основа:** дані ЛР1 та прогноз ЛР2  
**Трек:** А — класичний алгоритм управління

## Що реалізовано

- Моделі компонентів: СЕС, батарея, електромережа, навантаження.
- EMS-алгоритм для погодинного балансу: PV → load → battery → export; deficit → battery → grid.
- Тарифна оптимізація: заряд батареї у нічній зоні, розряд у піковій зоні.
- Симуляція 7 днів з кроком 1 година, початковий SOC = 50%.
- Розрахунок енергетичних і економічних показників: self-consumption, PV coverage, cycles, savings, payback, NPV, IRR.
- Візуалізації: енергобаланс, SOC, імпорт/експорт, економія за тарифними зонами, структура джерел.

## Як запустити

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python src/simulate.py
```

## Результати

- `outputs/tables/ems_simulation_results.csv`
- `outputs/tables/ems_summary_metrics.json`
- `outputs/figures/*.png`
