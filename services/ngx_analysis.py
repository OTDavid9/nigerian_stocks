"""
NGX Investment Decision Support System – Full Predictive Module
================================================================
- Fetches NGX price history
- Computes technical indicators
- Compares 10+ regression models (including ARIMA & Prophet)
  and 7+ classification models (tabular)
- Walk‑forward validation
- LLM‑ready report with best‑model forecast
"""

import json
import math
import statistics
import urllib.request
import warnings
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------
# sklearn
# ---------------------------------------------------------------------
from sklearn.linear_model import (
    LinearRegression, Ridge, Lasso, ElasticNet, LogisticRegression
)
from sklearn.tree import DecisionTreeRegressor, DecisionTreeClassifier
from sklearn.ensemble import (
    RandomForestRegressor, RandomForestClassifier,
    GradientBoostingRegressor, GradientBoostingClassifier
)
from sklearn.svm import SVR, SVC
from sklearn.neighbors import KNeighborsRegressor, KNeighborsClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.metrics import (
    mean_absolute_error, mean_squared_error, r2_score,
    accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
)
from sklearn.model_selection import TimeSeriesSplit

# ---------------------------------------------------------------------
# Optional gradient boosting
# ---------------------------------------------------------------------
try:
    from xgboost import XGBRegressor, XGBClassifier
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

try:
    from lightgbm import LGBMRegressor, LGBMClassifier
    LGBM_AVAILABLE = True
except ImportError:
    LGBM_AVAILABLE = False

try:
    from catboost import CatBoostRegressor, CatBoostClassifier
    CATBOOST_AVAILABLE = True
except ImportError:
    CATBOOST_AVAILABLE = False

# ---------------------------------------------------------------------
# Time‑series models
# ---------------------------------------------------------------------
try:
    from statsmodels.tsa.arima.model import ARIMA
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False

try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False

warnings.filterwarnings("ignore")

# =============================================================================
# 1. TECHNICAL ANALYSIS CLASS
# =============================================================================
class NGXStockAnalyzer:
    """Compute technical indicators from NGX price history."""

    def __init__(self, api_json: dict):
        self.symbol = api_json.get("symbol", "UNKNOWN")
        self.currency = api_json.get("currency", "NGN")
        self.raw_data = api_json.get("data", [])

        self.dates: List[datetime] = []
        self.closes: List[float] = []
        for rec in self.raw_data:
            if rec.get("close") is not None:
                try:
                    dt = datetime.strptime(rec["date"], "%Y-%m-%d")
                except (ValueError, KeyError):
                    continue
                self.dates.append(dt)
                self.closes.append(float(rec["close"]))

        # Sort chronologically
        sorted_pairs = sorted(zip(self.dates, self.closes), key=lambda x: x[0])
        if sorted_pairs:
            self.dates, self.closes = zip(*sorted_pairs)
            self.dates = list(self.dates)
            self.closes = list(self.closes)
        else:
            self.dates, self.closes = [], []

        self.n = len(self.closes)

    def basic_stats(self) -> Dict[str, float]:
        if self.n == 0:
            return {}
        return {
            "latest_price": self.closes[-1],
            "start_date": self.dates[0].strftime("%Y-%m-%d"),
            "end_date": self.dates[-1].strftime("%Y-%m-%d"),
            "trading_days": self.n,
            "min_price": min(self.closes),
            "max_price": max(self.closes),
            "avg_price": statistics.mean(self.closes),
        }

    def _daily_returns(self) -> List[float]:
        returns = []
        for i in range(1, self.n):
            if self.closes[i-1] != 0:
                returns.append((self.closes[i] - self.closes[i-1]) / self.closes[i-1])
        return returns

    def return_metrics(self) -> Dict[str, Optional[float]]:
        if self.n < 2:
            return {}
        rets = self._daily_returns()
        if not rets:
            return {}
        total_ret = (self.closes[-1] - self.closes[0]) / self.closes[0] if self.closes[0] != 0 else 0
        years = max(1, self.n / 252)
        ann_ret = (1 + total_ret) ** (1 / years) - 1 if total_ret > -1 else 0
        daily_vol = statistics.stdev(rets) if len(rets) > 1 else 0.0
        annual_vol = daily_vol * math.sqrt(252)
        return {
            "total_return_pct": round(total_ret * 100, 2),
            "annualised_return_pct": round(ann_ret * 100, 2),
            "annualised_volatility_pct": round(annual_vol * 100, 2),
        }

    def _sma(self, window: int) -> List[Optional[float]]:
        if window > self.n:
            return [None] * self.n
        sma = [None] * (window - 1)
        for i in range(window - 1, self.n):
            sma.append(statistics.mean(self.closes[i - window + 1 : i + 1]))
        return sma

    def moving_average_analysis(self) -> Dict:
        ma50 = self._sma(50)
        ma200 = self._sma(200)
        result = {
            "sma_50": round(ma50[-1], 2) if ma50 and ma50[-1] is not None else None,
            "sma_200": round(ma200[-1], 2) if ma200 and ma200[-1] is not None else None,
        }
        if result["sma_50"]:
            result["price_vs_sma50_pct"] = round(
                (self.closes[-1] - result["sma_50"]) / result["sma_50"] * 100, 2
            )
        if result["sma_200"]:
            result["price_vs_sma200_pct"] = round(
                (self.closes[-1] - result["sma_200"]) / result["sma_200"] * 100, 2
            )
        if result["sma_50"] and result["sma_200"]:
            cross = "none"
            for i in range(max(0, self.n - 10), self.n - 1):
                if ma50[i] and ma200[i] and ma50[i+1] and ma200[i+1]:
                    if ma50[i] <= ma200[i] and ma50[i+1] > ma200[i+1]:
                        cross = "golden_cross (bullish)"
                        break
                    elif ma50[i] >= ma200[i] and ma50[i+1] < ma200[i+1]:
                        cross = "death_cross (bearish)"
                        break
            if cross == "none":
                cross = "golden_cross" if result["sma_50"] > result["sma_200"] else "death_cross"
            result["cross_signal"] = cross
        return result

    def _price_n_days_ago(self, n_days: int) -> Optional[float]:
        target = self.dates[-1] - timedelta(days=n_days)
        for i in range(self.n - 1, -1, -1):
            if self.dates[i] <= target:
                return self.closes[i]
        return None

    def recent_performance(self) -> Dict:
        def perf(days: int) -> Optional[float]:
            prev = self._price_n_days_ago(days)
            if prev and prev != 0:
                return round((self.closes[-1] - prev) / prev * 100, 2)
            return None
        return {
            "1m_change_pct": perf(30),
            "3m_change_pct": perf(90),
            "6m_change_pct": perf(180),
            "1y_change_pct": perf(365),
        }

    def rsi(self, period: int = 14) -> Optional[float]:
        if self.n < period + 1:
            return None
        gains, losses = [], []
        for i in range(1, self.n):
            diff = self.closes[i] - self.closes[i-1]
            gains.append(diff if diff > 0 else 0)
            losses.append(-diff if diff < 0 else 0)
        avg_gain = statistics.mean(gains[:period])
        avg_loss = statistics.mean(losses[:period])
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        rsi_val = 100 - (100 / (1 + rs))
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            if avg_loss == 0:
                rsi_val = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi_val = 100 - (100 / (1 + rs))
        return round(rsi_val, 2)

    def _ema(self, period: int) -> List[Optional[float]]:
        if self.n < period:
            return [None] * self.n
        ema = [None] * (period - 1)
        multiplier = 2 / (period + 1)
        seed = statistics.mean(self.closes[:period])
        ema.append(seed)
        for i in range(period, self.n):
            ema.append((self.closes[i] - ema[-1]) * multiplier + ema[-1])
        return ema

    def macd(self) -> Dict[str, Optional[float]]:
        ema12 = self._ema(12)
        ema26 = self._ema(26)
        if ema12[-1] is None or ema26[-1] is None:
            return {}
        macd_line = [a - b if a is not None and b is not None else None for a, b in zip(ema12, ema26)]
        valid_macd = [(i, v) for i, v in enumerate(macd_line) if v is not None]
        if len(valid_macd) < 9:
            return {}
        signal = [None] * self.n
        first9 = [v for _, v in valid_macd[:9]]
        seed = statistics.mean(first9)
        signal[valid_macd[8][0]] = seed
        multiplier = 2 / (9 + 1)
        for idx, val in valid_macd[9:]:
            prev_signal = signal[idx-1] if signal[idx-1] is not None else seed
            signal[idx] = (val - prev_signal) * multiplier + prev_signal
        latest_macd = macd_line[-1]
        last_sig = None
        for s in reversed(signal):
            if s is not None:
                last_sig = s
                break
        if latest_macd is None or last_sig is None:
            return {}
        histogram = latest_macd - last_sig
        return {
            "macd_line": round(latest_macd, 4),
            "signal_line": round(last_sig, 4),
            "macd_histogram": round(histogram, 4),
            "macd_signal": "bullish (above signal)" if histogram > 0 else "bearish (below signal)",
        }

    def max_drawdown(self) -> Optional[float]:
        if self.n < 2:
            return None
        peak = self.closes[0]
        max_dd = 0.0
        for price in self.closes:
            if price > peak:
                peak = price
            dd = (peak - price) / peak
            if dd > max_dd:
                max_dd = dd
        return round(max_dd * 100, 2)

    def generate_report(self) -> str:
        stats = self.basic_stats()
        returns = self.return_metrics()
        ma = self.moving_average_analysis()
        perf = self.recent_performance()
        rsi_val = self.rsi(14)
        macd_data = self.macd()
        md = self.max_drawdown()

        lines = [f"Technical Analysis Report for {self.symbol} (NGX, {self.currency})"]
        lines.append("-" * 60)
        if stats:
            lines.append(f"Period: {stats['start_date']} to {stats['end_date']} ({stats['trading_days']} trading days)")
            lines.append(f"Latest Close: {stats['latest_price']:.2f}")
            lines.append(f"Min: {stats['min_price']:.2f}  Max: {stats['max_price']:.2f}  Avg: {stats['avg_price']:.2f}")
        if returns:
            lines.append(f"\nTotal Return: {returns['total_return_pct']}%")
            lines.append(f"Annualised Return: {returns['annualised_return_pct']}%")
            lines.append(f"Annualised Volatility: {returns['annualised_volatility_pct']}%")
        if ma:
            lines.append("\nMoving Averages:")
            if ma.get("sma_50"):
                lines.append(f"  SMA(50): {ma['sma_50']:.2f} (Price vs SMA: {ma.get('price_vs_sma50_pct', 'N/A')}%)")
            if ma.get("sma_200"):
                lines.append(f"  SMA(200): {ma['sma_200']:.2f} (Price vs SMA: {ma.get('price_vs_sma200_pct', 'N/A')}%)")
            if "cross_signal" in ma:
                lines.append(f"  MA Cross Signal: {ma['cross_signal']}")
        if perf:
            lines.append("\nRecent Performance:")
            for period, pct in perf.items():
                if pct is not None:
                    lines.append(f"  {period}: {pct}%")
        if rsi_val is not None:
            lines.append(f"\nRSI(14): {rsi_val:.2f}")
        if macd_data:
            lines.append("\nMACD:")
            lines.append(f"  MACD Line: {macd_data['macd_line']}")
            lines.append(f"  Signal Line: {macd_data['signal_line']}")
            lines.append(f"  Histogram: {macd_data['macd_histogram']} ({macd_data['macd_signal']})")
        if md is not None:
            lines.append(f"\nMax Drawdown: {md}%")
        lines.append("")
        return "\n".join(lines)


# =============================================================================
# 2. DATA FETCHING & CLEANING
# =============================================================================
def fetch_stock_data(symbol: str, range: str = "All") -> dict:
    url = f"https://nigerian-stocks.onrender.com/api/v1/history/ngx/{symbol}?range={range}"
    req = urllib.request.Request(url, headers={"accept": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def clean_prices(raw_data: dict) -> Tuple[List[datetime], List[float]]:
    dates, closes = [], []
    for rec in raw_data.get("data", []):
        if rec.get("close") is not None:
            try:
                dt = datetime.strptime(rec["date"], "%Y-%m-%d")
            except:
                continue
            dates.append(dt)
            closes.append(float(rec["close"]))
    pairs = sorted(zip(dates, closes))
    if pairs:
        dates, closes = zip(*pairs)
        return list(dates), list(closes)
    return [], []


# =============================================================================
# 3. FEATURE ENGINEERING (for tabular models)
# =============================================================================
def create_features(closes: List[float], lags=(1,2,3,5,10)) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    closes = np.array(closes)
    max_lag = max(lags)
    X, y_price, y_dir = [], [], []
    for i in range(max_lag, len(closes) - 1):
        features = [closes[i - lag] for lag in lags]
        X.append(features)
        y_price.append(closes[i + 1])
        y_dir.append(1 if closes[i + 1] > closes[i] else 0)
    return np.array(X), np.array(y_price), np.array(y_dir)


# =============================================================================
# 4. BASELINE METRICS
# =============================================================================
def baseline_price_mae(X, y_price):
    preds = X[:, 0]
    return mean_absolute_error(y_price, preds)

def baseline_direction_acc(y_dir):
    preds = np.ones_like(y_dir)
    return accuracy_score(y_dir, preds)


# =============================================================================
# 5. PREDICTOR CLASS WITH ALL MODELS
# =============================================================================
class NGXStockPredictor:
    def __init__(self, dates, closes, lags=(1,2,3,5,10), forecast_days=5,
                 use_arima=True, use_prophet=True):
        self.dates = dates
        self.closes = closes
        self.lags = lags
        self.max_lag = max(lags)
        self.forecast_days = forecast_days

        self.X, self.y_price, self.y_dir = create_features(closes, lags)
        if len(self.X) < 30:
            raise ValueError("Not enough data.")

        # Tabular regression models
        reg_models = {
            "Linear Reg": LinearRegression(),
            "Ridge": Ridge(alpha=1.0),
            "Lasso": Lasso(alpha=0.01, max_iter=10000),
            "ElasticNet": ElasticNet(alpha=0.01, l1_ratio=0.5, max_iter=10000),
            "DecisionTree": DecisionTreeRegressor(max_depth=5, random_state=42),
            "RandomForest": RandomForestRegressor(n_estimators=100, max_depth=5,
                                                  random_state=42, n_jobs=-1),
            "GradBoost": GradientBoostingRegressor(n_estimators=100, max_depth=3,
                                                   random_state=42),
            "KNN": KNeighborsRegressor(n_neighbors=5),
            "SVR": SVR(kernel='rbf', C=100, gamma='scale'),
        }
        if XGB_AVAILABLE:
            reg_models["XGBoost"] = XGBRegressor(n_estimators=100, max_depth=3,
                                                  random_state=42, verbosity=0)
        if LGBM_AVAILABLE:
            reg_models["LightGBM"] = LGBMRegressor(n_estimators=100, max_depth=3,
                                                    random_state=42, verbose=-1)
        if CATBOOST_AVAILABLE:
            reg_models["CatBoost"] = CatBoostRegressor(n_estimators=100, max_depth=3,
                                                       random_seed=42, silent=True)
        self.regression_models = reg_models

        # Tabular classification models
        cls_models = {
            "Logistic": LogisticRegression(max_iter=1000),
            "DecisionTree": DecisionTreeClassifier(max_depth=5, random_state=42),
            "RandomForest": RandomForestClassifier(n_estimators=100, max_depth=5,
                                                   random_state=42, n_jobs=-1),
            "GradBoost": GradientBoostingClassifier(n_estimators=100, max_depth=3,
                                                    random_state=42),
            "KNN": KNeighborsClassifier(n_neighbors=5),
            "SVC": SVC(kernel='rbf', C=100, gamma='scale', probability=True),
            "GaussianNB": GaussianNB(),
        }
        if XGB_AVAILABLE:
            cls_models["XGBoost"] = XGBClassifier(n_estimators=100, max_depth=3,
                                                   random_state=42, verbosity=0,
                                                   use_label_encoder=False, eval_metric='logloss')
        if LGBM_AVAILABLE:
            cls_models["LightGBM"] = LGBMClassifier(n_estimators=100, max_depth=3,
                                                    random_state=42, verbose=-1)
        if CATBOOST_AVAILABLE:
            cls_models["CatBoost"] = CatBoostClassifier(n_estimators=100, max_depth=3,
                                                        random_seed=42, silent=True)
        self.classification_models = cls_models

        # Time‑series models
        self.ts_models = {}
        if use_arima and STATSMODELS_AVAILABLE:
            self.ts_models["ARIMA"] = "arima"
        if use_prophet and PROPHET_AVAILABLE:
            self.ts_models["Prophet"] = "prophet"

        # Results containers
        self.reg_results = {}
        self.cls_results = {}
        self.ts_results = {}
        self.baseline_mae = None
        self.baseline_acc = None
        self.best_reg_name = None
        self.best_reg_model = None
        self.best_cls_name = None
        self.best_cls_model = None
        self.future_prices = []
        self.future_probs = []

    def evaluate_with_walk_forward(self, n_splits=5):
        tscv = TimeSeriesSplit(n_splits=n_splits)

        # Tabular models
        reg_collectors = {name: {"yp_true":[], "yp_pred":[]} for name in self.regression_models}
        cls_collectors = {name: {"yd_true":[], "yd_pred":[]} for name in self.classification_models}

        for train_idx, test_idx in tscv.split(self.X):
            X_train, X_test = self.X[train_idx], self.X[test_idx]
            yp_train, yp_test = self.y_price[train_idx], self.y_price[test_idx]
            yd_train, yd_test = self.y_dir[train_idx], self.y_dir[test_idx]

            for name, model in self.regression_models.items():
                model.fit(X_train, yp_train)
                yp_pred = model.predict(X_test)
                reg_collectors[name]["yp_true"].extend(yp_test)
                reg_collectors[name]["yp_pred"].extend(yp_pred)

            for name, model in self.classification_models.items():
                model.fit(X_train, yd_train)
                yd_pred = model.predict(X_test)
                cls_collectors[name]["yd_true"].extend(yd_test)
                cls_collectors[name]["yd_pred"].extend(yd_pred)

        # Compute tabular regression metrics
        for name, data in reg_collectors.items():
            yp_true = np.array(data["yp_true"])
            yp_pred = np.array(data["yp_pred"])
            mae = mean_absolute_error(yp_true, yp_pred)
            rmse = np.sqrt(mean_squared_error(yp_true, yp_pred))
            mask = yp_true != 0
            mape = (np.mean(np.abs((yp_true[mask] - yp_pred[mask]) / yp_true[mask])) * 100
                    if mask.sum() > 0 else float('inf'))
            r2 = r2_score(yp_true, yp_pred)
            self.reg_results[name] = {"MAE": mae, "RMSE": rmse, "MAPE": mape, "R²": r2}

        # Compute tabular classification metrics
        for name, data in cls_collectors.items():
            yd_true = np.array(data["yd_true"])
            yd_pred = np.array(data["yd_pred"])
            acc = accuracy_score(yd_true, yd_pred)
            prec = precision_score(yd_true, yd_pred, zero_division=0)
            rec = recall_score(yd_true, yd_pred, zero_division=0)
            f1 = f1_score(yd_true, yd_pred, zero_division=0)
            cm = confusion_matrix(yd_true, yd_pred)
            self.cls_results[name] = {"Acc": acc, "Prec": prec, "Rec": rec, "F1": f1, "CM": cm}

        # Time‑series models (walk‑forward on raw closes)
        folds = list(tscv.split(np.arange(len(self.closes))))
        for train_idx, test_idx in folds:
            if len(train_idx) < self.max_lag + 1:
                continue
            train_closes = [self.closes[i] for i in train_idx]
            test_closes = [self.closes[i] for i in test_idx]

            for ts_name in self.ts_models:
                if ts_name not in self.ts_results:
                    self.ts_results[ts_name] = {"yp_true":[], "yp_pred":[]}
                if ts_name == "ARIMA":
                    try:
                        model = ARIMA(train_closes, order=(5,1,0))
                        fitted = model.fit()
                        yp_pred = fitted.forecast(steps=len(test_closes))
                    except:
                        yp_pred = [train_closes[-1]] * len(test_closes)
                elif ts_name == "Prophet":
                    try:
                        train_df = pd.DataFrame({'ds': [self.dates[i] for i in train_idx],
                                                 'y': train_closes})
                        model = Prophet()
                        model.fit(train_df)
                        future_df = pd.DataFrame({'ds': [self.dates[i] for i in test_idx]})
                        forecast = model.predict(future_df)
                        yp_pred = forecast['yhat'].values
                    except:
                        yp_pred = [train_closes[-1]] * len(test_closes)
                else:
                    yp_pred = [train_closes[-1]] * len(test_closes)
                self.ts_results[ts_name]["yp_true"].extend(test_closes)
                self.ts_results[ts_name]["yp_pred"].extend(yp_pred)

        # Compute TS metrics
        for ts_name in self.ts_models:
            data = self.ts_results[ts_name]
            yp_true = np.array(data["yp_true"])
            yp_pred = np.array(data["yp_pred"])
            mae = mean_absolute_error(yp_true, yp_pred)
            rmse = np.sqrt(mean_squared_error(yp_true, yp_pred))
            mask = yp_true != 0
            mape = (np.mean(np.abs((yp_true[mask] - yp_pred[mask]) / yp_true[mask])) * 100
                    if mask.sum() > 0 else float('inf'))
            r2 = r2_score(yp_true, yp_pred)
            self.reg_results[ts_name] = {"MAE": mae, "RMSE": rmse, "MAPE": mape, "R²": r2}

        # Baselines
        self.baseline_mae = baseline_price_mae(self.X, self.y_price)
        self.baseline_acc = baseline_direction_acc(self.y_dir)

    def train_final_models(self, reg_metric='MAE'):
        if not self.reg_results or not self.cls_results:
            raise RuntimeError("Run evaluate first.")
        # Best regression
        self.best_reg_name = min(self.reg_results, key=lambda k: self.reg_results[k][reg_metric])
        if self.best_reg_name in self.regression_models:
            self.best_reg_model = self.regression_models[self.best_reg_name]
            self.best_reg_model.fit(self.X, self.y_price)
        elif self.best_reg_name == "ARIMA":
            self.best_reg_model = "ARIMA"
        elif self.best_reg_name == "Prophet":
            self.best_reg_model = "Prophet"
        else:
            self.best_reg_model = LinearRegression()
            self.best_reg_model.fit(self.X, self.y_price)

        # Best classification
        self.best_cls_name = max(self.cls_results, key=lambda k: self.cls_results[k]['Acc'])
        self.best_cls_model = self.classification_models[self.best_cls_name]
        self.best_cls_model.fit(self.X, self.y_dir)

    def forecast_future(self):
        if not self.best_reg_model:
            raise RuntimeError("Train final models first.")
        preds = []
        probs = []
        last_prices = list(self.closes[-self.max_lag:])

        if self.best_reg_name in self.regression_models:
            for _ in range(self.forecast_days):
                feat = [last_prices[-lag] for lag in self.lags]
                feat_arr = np.array(feat).reshape(1, -1)
                next_close = float(self.best_reg_model.predict(feat_arr)[0])
                next_close = max(0.0, next_close)
                preds.append(next_close)
                last_prices.append(next_close)
            # Direction probs from best classifier
            if hasattr(self.best_cls_model, "predict_proba"):
                probs = [float(self.best_cls_model.predict_proba(feat_arr)[0][1]) for _ in range(self.forecast_days)]
            else:
                probs = [0.5] * self.forecast_days
        elif self.best_reg_name == "ARIMA":
            try:
                model = ARIMA(self.closes, order=(5,1,0))
                fitted = model.fit()
                forecast = fitted.forecast(steps=self.forecast_days)
                preds = list(forecast)
            except:
                preds = [self.closes[-1]] * self.forecast_days
            probs = [0.5] * self.forecast_days
        elif self.best_reg_name == "Prophet":
            try:
                df = pd.DataFrame({'ds': self.dates, 'y': self.closes})
                model = Prophet()
                model.fit(df)
                future = model.make_future_dataframe(periods=self.forecast_days)
                forecast = model.predict(future)
                preds = list(forecast['yhat'].values[-self.forecast_days:])
            except:
                preds = [self.closes[-1]] * self.forecast_days
            probs = [0.5] * self.forecast_days

        self.future_prices = preds
        self.future_probs = probs

    def generate_prediction_report(self) -> str:
        lines = ["Multi‑Model Predictive Analysis"]
        lines.append("=" * 60)
        lines.append(f"Validation: Walk‑forward ({len(self.X)} samples, 5 folds)")
        lines.append(f"Features (tabular): lagged close prices at {self.lags}")

        # Regression table
        lines.append("\n--- Regression Models (Price Prediction) ---")
        header = f"{'Model':<20} {'MAE':>8} {'RMSE':>8} {'MAPE':>8} {'R²':>8}"
        lines.append(header)
        lines.append("-" * len(header))
        for name, m in sorted(self.reg_results.items(), key=lambda x: x[1]['MAE']):
            lines.append(f"{name:<20} {m['MAE']:8.4f} {m['RMSE']:8.4f} {m['MAPE']:8.2f}% {m['R²']:8.4f}")
        lines.append(f"\nBaseline (persistence) MAE: {self.baseline_mae:.4f}")
        lines.append(f"Best price model: {self.best_reg_name}")

        # Classification table
        lines.append("\n--- Classification Models (Direction Prediction) ---")
        header = f"{'Model':<20} {'Acc':>8} {'Prec':>8} {'Rec':>8} {'F1':>8}"
        lines.append(header)
        lines.append("-" * len(header))
        for name, m in sorted(self.cls_results.items(), key=lambda x: x[1]['Acc'], reverse=True):
            lines.append(f"{name:<20} {m['Acc']:8.4f} {m['Prec']:8.4f} {m['Rec']:8.4f} {m['F1']:8.4f}")
        lines.append(f"\nBaseline (always 'up') Accuracy: {self.baseline_acc:.4f}")
        lines.append(f"Best direction model: {self.best_cls_name}")

        # Forecast
        lines.append(f"\nNext {self.forecast_days}-Day Forecast (best price model: {self.best_reg_name})")
        for i, (p, prob) in enumerate(zip(self.future_prices, self.future_probs), 1):
            direction = "Up" if prob > 0.5 else "Down"
            lines.append(f"  Day {i}: ₦{p:.2f}  (Prob. Up: {prob:.2f}, {direction})")
        avg_pred = np.mean(self.future_prices)
        trend = "upward" if avg_pred > self.closes[-1] else "downward"
        lines.append(f"Overall trend: {trend} (avg forecast ₦{avg_pred:.2f} vs. last close ₦{self.closes[-1]:.2f})")

        # Reliability
        best_mape = self.reg_results[self.best_reg_name]["MAPE"]
        best_acc = self.cls_results[self.best_cls_name]["Acc"]
        if best_mape < 5 and best_acc > 0.6:
            rel = "High"
        elif best_mape < 10:
            rel = "Moderate"
        else:
            rel = "Low – forecasts may be noisy"
        lines.append(f"Model Reliability: {rel}")
        return "\n".join(lines)


# =============================================================================
# 6. MASTER FUNCTION
# =============================================================================
def generate_full_report(symbol: str, range: str = "All") -> str:
    raw = fetch_stock_data(symbol, range)
    dates, closes = clean_prices(raw)
    if len(closes) < 60:
        return f"ERROR: {symbol} has only {len(closes)} days – need ≥60."

    # Technical analysis
    ta = NGXStockAnalyzer(raw)
    tech_report = ta.generate_report()

    # Predictive analysis
    try:
        pred = NGXStockPredictor(dates, closes, forecast_days=5)
        pred.evaluate_with_walk_forward(n_splits=5)
        pred.train_final_models()
        pred.forecast_future()
        pred_report = pred.generate_prediction_report()
    except Exception as e:
        pred_report = f"Predictive analysis failed: {str(e)}"

    full = f"Investment Analysis for {symbol.upper()} (NGX)\n{'='*60}\n\n"
    full += tech_report + "\n" + pred_report
    return full


# =============================================================================
# 7. EXAMPLE USAGE
# =============================================================================
# if __name__ == "__main__":
#     symbol = "OANDO"
#     print(f"Generating report for {symbol}...\n")
#     report = generate_full_report(symbol)
#     print(report)