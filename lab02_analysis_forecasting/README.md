# Лабораторна робота №2 — Аналіз даних та прогнозування енергоспоживання

**Варіант:** 3 — Лабораторія, Київ, 2025  
**Основа:** дані з ЛР1 (`data/energy_lab1_v3.sqlite`)  
**Трек:** А — класичний Data Science підхід

## Що реалізовано

- EDA: описові статистики, часові профілі, сезонність, тренди, пропущені значення, викиди, автокореляція.
- Факторний аналіз: HDD, CDD, температура, тарифна зона, години, день тижня, режим роботи.
- Feature engineering: циклічне кодування часу, лаги 24/168 год, ковзаючі статистики.
- Моделі: Linear Regression, Multiple Linear Regression, Polynomial Regression, Random Forest, Gradient Boosting.
- Оцінювання: R², RMSE, MAE, MAPE.
- Прогноз на наступний місяць з довірчим інтервалом і вартістю.
- Мінімум 10 візуалізацій у `outputs/figures/`.

## Як запустити

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python src/run_analysis.py
```

## Результати

- `outputs/tables/descriptive_statistics.csv`
- `outputs/tables/model_metrics.csv`
- `outputs/tables/forecast_next_month.csv`
- `outputs/figures/*.png`
- `notebooks/energy_analysis_forecast.ipynb`
