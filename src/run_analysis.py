"""Exploratory analysis and forecasting for Lab 2, Variant 3."""
from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "energy_lab1_v3.sqlite"
FIG_DIR = ROOT / "outputs" / "figures"
TABLE_DIR = ROOT / "outputs" / "tables"
FIG_DIR.mkdir(parents=True, exist_ok=True)
TABLE_DIR.mkdir(parents=True, exist_ok=True)

AREA_M2 = 600.0
WORK_START = 6
WORK_END = 22
RANDOM_STATE = 303


def load_dataset() -> pd.DataFrame:
    """Load main-meter consumption with weather, tariff and baseline data."""
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query(
            """
            SELECT
                ms.timestamp,
                ms.consumption_kwh,
                w.temperature_c,
                w.insolation_kw_m2,
                w.hdd_18,
                w.cdd_22,
                b.baseline_kwh,
                ts.zone_name,
                ts.import_price_uah_kwh
            FROM measurements ms
            JOIN meters m ON m.meter_id = ms.meter_id AND m.accounting_level = 1
            JOIN weather_data w ON w.object_id = m.object_id AND w.timestamp = ms.timestamp
            JOIN baselines b ON b.object_id = m.object_id AND b.timestamp = ms.timestamp
            JOIN tariff_schedule ts ON ts.hour = CAST(STRFTIME('%H', ms.timestamp) AS INTEGER)
            ORDER BY ms.timestamp
            """,
            conn,
            parse_dates=["timestamp"],
        )
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create time, weather and lag features."""
    data = df.copy()
    ts = data["timestamp"]
    data["hour"] = ts.dt.hour
    data["dayofweek"] = ts.dt.dayofweek
    data["month"] = ts.dt.month
    data["dayofyear"] = ts.dt.dayofyear
    data["is_weekend"] = (data["dayofweek"] >= 5).astype(int)
    data["is_operating_hour"] = ((data["hour"] >= WORK_START) & (data["hour"] < WORK_END)).astype(int)

    data["hour_sin"] = np.sin(2 * np.pi * data["hour"] / 24)
    data["hour_cos"] = np.cos(2 * np.pi * data["hour"] / 24)
    data["dow_sin"] = np.sin(2 * np.pi * data["dayofweek"] / 7)
    data["dow_cos"] = np.cos(2 * np.pi * data["dayofweek"] / 7)
    data["month_sin"] = np.sin(2 * np.pi * data["month"] / 12)
    data["month_cos"] = np.cos(2 * np.pi * data["month"] / 12)

    data["lag_24"] = data["consumption_kwh"].shift(24)
    data["lag_168"] = data["consumption_kwh"].shift(168)
    data["roll_24_mean"] = data["consumption_kwh"].shift(1).rolling(24).mean()
    data["roll_24_std"] = data["consumption_kwh"].shift(1).rolling(24).std()
    data["specific_kwh_m2"] = data["consumption_kwh"] / AREA_M2
    return data


def mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean absolute percentage error with zero-protection."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    return float(np.mean(np.abs((y_true - y_pred) / np.maximum(np.abs(y_true), 1e-6))) * 100)


def calc_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Calculate regression quality metrics."""
    return {
        "R2": round(float(r2_score(y_true, y_pred)), 4),
        "RMSE": round(float(math.sqrt(mean_squared_error(y_true, y_pred))), 4),
        "MAE": round(float(mean_absolute_error(y_true, y_pred)), 4),
        "MAPE_pct": round(mape(y_true, y_pred), 4),
    }


def save_plot(path: Path) -> None:
    """Apply standard layout and save current matplotlib figure."""
    plt.tight_layout()
    plt.savefig(path, dpi=170)
    plt.close()


def create_visualizations(df: pd.DataFrame, featured: pd.DataFrame) -> None:
    """Create required EDA visualizations."""
    data = df.copy()
    data["date"] = data["timestamp"].dt.date
    daily = data.groupby("date", as_index=False)["consumption_kwh"].sum()

    plt.figure(figsize=(12, 4))
    plt.plot(pd.to_datetime(daily["date"]), daily["consumption_kwh"])
    plt.title("Річна динаміка добового споживання")
    plt.xlabel("Дата")
    plt.ylabel("кВт·год/добу")
    save_plot(FIG_DIR / "01_year_daily_consumption.png")

    plt.figure(figsize=(8, 4))
    plt.hist(data["consumption_kwh"], bins=45)
    plt.title("Розподіл погодинного споживання")
    plt.xlabel("кВт·год")
    plt.ylabel("Кількість годин")
    save_plot(FIG_DIR / "02_consumption_histogram.png")

    data["month"] = data["timestamp"].dt.month
    grouped = [data.loc[data["month"] == m, "consumption_kwh"].values for m in range(1, 13)]
    plt.figure(figsize=(10, 5))
    plt.boxplot(grouped, labels=[str(m) for m in range(1, 13)], showfliers=False)
    plt.title("Box plot споживання за місяцями")
    plt.xlabel("Місяць")
    plt.ylabel("кВт·год")
    save_plot(FIG_DIR / "03_monthly_boxplot.png")

    data["hour"] = data["timestamp"].dt.hour
    profile = data.groupby("hour")["consumption_kwh"].mean()
    plt.figure(figsize=(9, 4))
    plt.plot(profile.index, profile.values, marker="o")
    plt.title("Типовий добовий профіль")
    plt.xlabel("Година")
    plt.ylabel("Середнє кВт·год")
    save_plot(FIG_DIR / "04_daily_profile.png")

    data["is_weekend"] = data["timestamp"].dt.dayofweek >= 5
    profile_week = data.groupby(["is_weekend", "hour"])["consumption_kwh"].mean().unstack(0)
    plt.figure(figsize=(9, 4))
    plt.plot(profile_week.index, profile_week[False], marker="o", label="Робочі дні")
    plt.plot(profile_week.index, profile_week[True], marker="o", label="Вихідні")
    plt.title("Порівняння робочих та вихідних днів")
    plt.xlabel("Година")
    plt.ylabel("Середнє кВт·год")
    plt.legend()
    save_plot(FIG_DIR / "05_workday_weekend_profile.png")

    monthly = data.set_index("timestamp").resample("MS")["consumption_kwh"].sum()
    plt.figure(figsize=(10, 4))
    plt.bar(monthly.index.strftime("%Y-%m"), monthly.values)
    plt.title("Місячна динаміка споживання")
    plt.xlabel("Місяць")
    plt.ylabel("кВт·год")
    plt.xticks(rotation=45, ha="right")
    save_plot(FIG_DIR / "06_monthly_consumption.png")

    data["weekday"] = data["timestamp"].dt.dayofweek
    heat = data.pivot_table(values="consumption_kwh", index="hour", columns="weekday", aggfunc="mean")
    plt.figure(figsize=(8, 6))
    plt.imshow(heat.values, aspect="auto", origin="lower")
    plt.colorbar(label="кВт·год")
    plt.title("Heatmap: години × дні тижня")
    plt.xlabel("День тижня, 0=Пн")
    plt.ylabel("Година")
    plt.xticks(range(7), ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"])
    plt.yticks(range(0, 24, 2))
    save_plot(FIG_DIR / "07_heatmap_hour_weekday.png")

    rolling = data.set_index("timestamp")["consumption_kwh"].rolling(24 * 14, min_periods=24).mean()
    plt.figure(figsize=(12, 4))
    plt.plot(data["timestamp"], data["consumption_kwh"], alpha=0.3, label="Факт")
    plt.plot(rolling.index, rolling.values, linewidth=2, label="Тренд, 14 днів")
    plt.title("Декомпозиція: ряд і згладжений тренд")
    plt.xlabel("Дата")
    plt.ylabel("кВт·год")
    plt.legend()
    save_plot(FIG_DIR / "08_trend_decomposition.png")

    lags = range(1, 169)
    autocorr = [data["consumption_kwh"].autocorr(lag=i) for i in lags]
    plt.figure(figsize=(10, 4))
    plt.plot(list(lags), autocorr)
    plt.title("Автокореляція до 168 годин")
    plt.xlabel("Лаг, год")
    plt.ylabel("ACF")
    save_plot(FIG_DIR / "09_autocorrelation.png")

    corr_cols = ["consumption_kwh", "temperature_c", "hdd_18", "cdd_22", "insolation_kw_m2", "import_price_uah_kwh"]
    corr = data[corr_cols].corr()
    plt.figure(figsize=(8, 6))
    plt.imshow(corr.values, vmin=-1, vmax=1)
    plt.colorbar(label="Кореляція")
    plt.xticks(range(len(corr_cols)), corr_cols, rotation=45, ha="right")
    plt.yticks(range(len(corr_cols)), corr_cols)
    for i in range(len(corr_cols)):
        for j in range(len(corr_cols)):
            plt.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", fontsize=8)
    plt.title("Кореляційна матриця факторів")
    save_plot(FIG_DIR / "10_correlation_matrix.png")

    # Missing values/outlier diagnostic.
    z = (data["consumption_kwh"] - data["consumption_kwh"].mean()) / data["consumption_kwh"].std()
    plt.figure(figsize=(12, 3.8))
    plt.scatter(data["timestamp"], z, s=4)
    plt.axhline(3, linestyle="--")
    plt.axhline(-3, linestyle="--")
    plt.title("Діагностика викидів за z-score")
    plt.xlabel("Дата")
    plt.ylabel("z-score")
    save_plot(FIG_DIR / "11_outlier_diagnostics.png")


def train_models(featured: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, object, list[str], pd.DataFrame]:
    """Train and evaluate several forecasting models."""
    model_data = featured.dropna().reset_index(drop=True)
    split_idx = int(len(model_data) * 0.80)
    train = model_data.iloc[:split_idx]
    test = model_data.iloc[split_idx:]

    simple_features = ["temperature_c", "is_operating_hour"]
    selected_features = [
        "temperature_c", "insolation_kw_m2", "hdd_18", "cdd_22", "import_price_uah_kwh",
        "hour_sin", "hour_cos", "dow_sin", "dow_cos", "month_sin", "month_cos",
        "is_weekend", "is_operating_hour", "lag_24", "lag_168", "roll_24_mean", "roll_24_std",
    ]
    poly_features = ["temperature_c", "hdd_18", "cdd_22", "hour_sin", "hour_cos", "is_operating_hour"]

    models = {
        "Simple Linear Regression": (LinearRegression(), simple_features),
        "Multiple Linear Regression": (Pipeline([("scaler", StandardScaler()), ("lr", LinearRegression())]), selected_features),
        "Polynomial Regression": (Pipeline([("poly", PolynomialFeatures(degree=2, include_bias=False)), ("scaler", StandardScaler()), ("lr", LinearRegression())]), poly_features),
        "Random Forest": (RandomForestRegressor(n_estimators=140, max_depth=16, random_state=RANDOM_STATE, n_jobs=-1), selected_features),
        "Gradient Boosting": (GradientBoostingRegressor(random_state=RANDOM_STATE, n_estimators=220, learning_rate=0.045, max_depth=3), selected_features),
    }

    y_train = train["consumption_kwh"]
    y_test = test["consumption_kwh"]
    metrics_rows = []
    predictions = test[["timestamp", "consumption_kwh"]].copy()
    fitted: dict[str, tuple[object, list[str]]] = {}
    for name, (model, cols) in models.items():
        model.fit(train[cols], y_train)
        pred = model.predict(test[cols])
        predictions[name] = pred
        row = {"model": name, **calc_metrics(y_test, pred)}
        metrics_rows.append(row)
        fitted[name] = (model, cols)

    metrics = pd.DataFrame(metrics_rows).sort_values(["RMSE", "MAE"]).reset_index(drop=True)
    best_name = str(metrics.iloc[0]["model"])
    best_model, best_features = fitted[best_name]

    metrics.to_csv(TABLE_DIR / "model_metrics.csv", index=False, encoding="utf-8-sig")
    predictions.to_csv(TABLE_DIR / "test_predictions.csv", index=False, encoding="utf-8-sig")

    plt.figure(figsize=(12, 4))
    plt.plot(predictions["timestamp"], predictions["consumption_kwh"], label="Факт")
    plt.plot(predictions["timestamp"], predictions[best_name], label=f"Прогноз: {best_name}")
    plt.title("Факт vs прогноз на тестовому періоді")
    plt.xlabel("Дата")
    plt.ylabel("кВт·год")
    plt.legend()
    save_plot(FIG_DIR / "12_actual_vs_prediction.png")

    residuals = predictions["consumption_kwh"] - predictions[best_name]
    plt.figure(figsize=(9, 4))
    plt.hist(residuals, bins=40)
    plt.title("Розподіл залишків найкращої моделі")
    plt.xlabel("Залишок, кВт·год")
    plt.ylabel("Кількість")
    save_plot(FIG_DIR / "13_residuals_histogram.png")

    if hasattr(best_model, "feature_importances_"):
        importances = pd.Series(best_model.feature_importances_, index=best_features).sort_values(ascending=False).head(12)
        plt.figure(figsize=(9, 5))
        plt.barh(importances.index[::-1], importances.values[::-1])
        plt.title("Важливість ознак найкращої моделі")
        plt.xlabel("Importance")
        save_plot(FIG_DIR / "14_feature_importance.png")
    elif hasattr(best_model, "named_steps") and hasattr(best_model.named_steps.get("lr"), "coef_"):
        coefs = pd.Series(best_model.named_steps["lr"].coef_[: len(best_features)], index=best_features).abs().sort_values(ascending=False).head(12)
        plt.figure(figsize=(9, 5))
        plt.barh(coefs.index[::-1], coefs.values[::-1])
        plt.title("Оцінка впливу ознак за коефіцієнтами")
        plt.xlabel("|коефіцієнт|")
        save_plot(FIG_DIR / "14_feature_importance.png")

    best_pack = pd.DataFrame({"best_model": [best_name], "features": [json.dumps(best_features, ensure_ascii=False)]})
    best_pack.to_csv(TABLE_DIR / "best_model.csv", index=False, encoding="utf-8-sig")
    return metrics, predictions, best_model, best_features, model_data


def synthetic_weather_for_future(timestamps: pd.DatetimeIndex) -> pd.DataFrame:
    """Generate deterministic future weather features for January 2026."""
    doy = timestamps.dayofyear.to_numpy()
    hour = timestamps.hour.to_numpy()
    annual = 9.0 + 13.5 * np.sin(2 * np.pi * (doy - 105) / 365.0)
    daily = 3.8 * np.sin(2 * np.pi * (hour - 8) / 24.0)
    temperature = annual + daily
    daylight = np.maximum(0, np.sin(np.pi * (hour - 6) / 12.0))
    seasonal_solar = np.clip(0.35 + 0.65 * np.sin(2 * np.pi * (doy - 80) / 365.0), 0.12, 1.0)
    insolation = np.clip(daylight * seasonal_solar * 0.78, 0, 1.0)
    return pd.DataFrame({
        "timestamp": timestamps,
        "temperature_c": temperature,
        "insolation_kw_m2": insolation,
        "hdd_18": np.maximum(18 - temperature, 0),
        "cdd_22": np.maximum(temperature - 22, 0),
    })


def tariff_price(hour: int) -> tuple[str, float]:
    if 23 <= hour or hour < 7:
        return "night", 5.6
    if 8 <= hour < 11 or 17 <= hour < 22:
        return "peak", 9.0
    return "half_peak", 6.9


def make_future_frame(history: pd.DataFrame, model_data: pd.DataFrame) -> pd.DataFrame:
    """Build feature frame for the next month forecast."""
    start = history["timestamp"].max() + pd.Timedelta(hours=1)
    end = start + pd.offsets.MonthEnd(1) + pd.Timedelta(hours=23)
    timestamps = pd.date_range(start, end, freq="h")
    future = synthetic_weather_for_future(timestamps)
    future["zone_name"] = [tariff_price(h)[0] for h in future["timestamp"].dt.hour]
    future["import_price_uah_kwh"] = [tariff_price(h)[1] for h in future["timestamp"].dt.hour]
    future["baseline_kwh"] = np.nan
    future["consumption_kwh"] = np.nan

    future = add_features(future)
    # Use typical values from the last 8 weeks for lag/rolling features.
    hist = model_data.copy()
    hist["hour"] = hist["timestamp"].dt.hour
    hist["dayofweek"] = hist["timestamp"].dt.dayofweek
    typical_hd = hist.groupby(["dayofweek", "hour"])["consumption_kwh"].mean()
    typical_h = hist.groupby("hour")["consumption_kwh"].mean()

    lag_24 = []
    lag_168 = []
    roll_mean = []
    roll_std = []
    for ts in future["timestamp"]:
        key = (ts.dayofweek, ts.hour)
        lag_168.append(float(typical_hd.get(key, hist["consumption_kwh"].mean())))
        lag_24.append(float(typical_h.get(ts.hour, hist["consumption_kwh"].mean())))
        similar = hist[(hist["hour"] == ts.hour) | (hist["dayofweek"] == ts.dayofweek)]["consumption_kwh"]
        roll_mean.append(float(similar.mean()))
        roll_std.append(float(similar.std()))
    future["lag_24"] = lag_24
    future["lag_168"] = lag_168
    future["roll_24_mean"] = roll_mean
    future["roll_24_std"] = roll_std
    future["specific_kwh_m2"] = np.nan
    return future


def forecast_next_month(best_model: object, best_features: list[str], history: pd.DataFrame, model_data: pd.DataFrame, predictions: pd.DataFrame) -> pd.DataFrame:
    """Create next-month forecast with a simple residual confidence interval."""
    future = make_future_frame(history, model_data)
    yhat = best_model.predict(future[best_features])
    best_model_name = pd.read_csv(TABLE_DIR / "best_model.csv")["best_model"].iloc[0]
    residual_std = float((predictions["consumption_kwh"] - predictions[best_model_name]).std())
    future["forecast_kwh"] = np.maximum(yhat, 0)
    future["lower_95_kwh"] = np.maximum(future["forecast_kwh"] - 1.96 * residual_std, 0)
    future["upper_95_kwh"] = future["forecast_kwh"] + 1.96 * residual_std
    future["forecast_cost_uah"] = future["forecast_kwh"] * future["import_price_uah_kwh"]
    out = future[["timestamp", "forecast_kwh", "lower_95_kwh", "upper_95_kwh", "zone_name", "import_price_uah_kwh", "forecast_cost_uah"]]
    out.to_csv(TABLE_DIR / "forecast_next_month.csv", index=False, encoding="utf-8-sig")

    plt.figure(figsize=(12, 4))
    plt.plot(out["timestamp"], out["forecast_kwh"], label="Прогноз")
    plt.fill_between(out["timestamp"], out["lower_95_kwh"], out["upper_95_kwh"], alpha=0.2, label="95% інтервал")
    plt.title("Прогноз споживання на наступний місяць")
    plt.xlabel("Дата")
    plt.ylabel("кВт·год")
    plt.legend()
    save_plot(FIG_DIR / "15_next_month_forecast.png")
    return out


def save_descriptive_tables(df: pd.DataFrame, featured: pd.DataFrame) -> None:
    """Save descriptive statistics and quality diagnostics."""
    desc = df[["consumption_kwh", "temperature_c", "insolation_kw_m2", "hdd_18", "cdd_22", "baseline_kwh"]].describe().T
    desc.to_csv(TABLE_DIR / "descriptive_statistics.csv", encoding="utf-8-sig")

    diagnostics = pd.DataFrame({
        "metric": ["rows", "missing_values", "duplicated_timestamps", "outliers_z_gt_3"],
        "value": [
            len(df),
            int(df.isna().sum().sum()),
            int(df["timestamp"].duplicated().sum()),
            int(((df["consumption_kwh"] - df["consumption_kwh"].mean()).abs() > 3 * df["consumption_kwh"].std()).sum()),
        ],
    })
    diagnostics.to_csv(TABLE_DIR / "data_quality_diagnostics.csv", index=False, encoding="utf-8-sig")

    factor_corr = df[["consumption_kwh", "temperature_c", "hdd_18", "cdd_22", "insolation_kw_m2", "import_price_uah_kwh"]].corr()["consumption_kwh"].sort_values(ascending=False)
    factor_corr.to_csv(TABLE_DIR / "factor_correlations.csv", encoding="utf-8-sig")


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")
    df = load_dataset()
    featured = add_features(df)
    save_descriptive_tables(df, featured)
    create_visualizations(df, featured)
    metrics, predictions, best_model, best_features, model_data = train_models(featured)
    forecast = forecast_next_month(best_model, best_features, df, model_data, predictions)

    summary = {
        "rows": int(len(df)),
        "best_model": str(metrics.iloc[0]["model"]),
        "best_rmse": float(metrics.iloc[0]["RMSE"]),
        "best_mape_pct": float(metrics.iloc[0]["MAPE_pct"]),
        "next_month_forecast_kwh": round(float(forecast["forecast_kwh"].sum()), 2),
        "next_month_forecast_cost_uah": round(float(forecast["forecast_cost_uah"].sum()), 2),
    }
    (TABLE_DIR / "analysis_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
