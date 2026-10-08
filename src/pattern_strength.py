"""
Siła formacji harmonicznej (0-100) - z tego, co sidebar już pokazuje, z wagami wyuczonymi na wynikach.

Cechy (te same dla formacji z wykresu i setupów z src/harmonic_setups.py):
- konfluencje z confluences_json: każdy typ osobno jako zgodny / przeciwny kierunkowi formacji
  (kierunki i kategorie 1:1 z sidebara frontu - CONFLUENCE_CATALOG), pokrycie 5 kategorii sidebara,
  liczba konfluencji zgodnych i przeciwnych;
- typ formacji, interwał, wielkość struktury (peak spacing), odchylenie proporcji od definicji
  (src/harmonic_validation.py, 0 = idealnie w zakresach).

Model: regresja logistyczna z regularyzacją L2 (numpy, IRLS) przewidująca, czy setup dojdzie do TP1
przed SL. Uczony na rozstrzygniętych setupach (wejście jest w chwili, w której konfluencje są
liczone przyczynowo - patrz analysis_services/setup_tracking_service.py). Walidacja: najstarsze
TRAIN_SHARE setupów uczy, najnowsze testują (AUC, win rate i średnie R w kwintylach) - potem model
produkcyjny uczony na całości. Wynik "score" to percentyl przewidywania wśród wszystkich setupów
uczących: 100 = najsilniejsze, 50 = mediana.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .harmonic_validation import Point, ValidationError, validate_xabcd

# typ -> (kategoria sidebara, kierunek); "both" = neutralna względem kierunku formacji
CONFLUENCE_CATALOG: Dict[str, Tuple[str, str]] = {
    "rsi_oversold": ("momentum", "bullish"), "rsi_overbought": ("momentum", "bearish"),
    "rsi_bullish_divergence": ("momentum", "bullish"), "rsi_bearish_divergence": ("momentum", "bearish"),
    "stochastic_oversold": ("momentum", "bullish"), "stochastic_overbought": ("momentum", "bearish"),
    "bullish_engulfing": ("candles", "bullish"), "bearish_engulfing": ("candles", "bearish"),
    "bullish_pin_bar": ("candles", "bullish"), "bearish_pin_bar": ("candles", "bearish"),
    "hammer": ("candles", "bullish"), "shooting_star": ("candles", "bearish"),
    "morning_star": ("candles", "bullish"), "evening_star": ("candles", "bearish"), "doji": ("candles", "both"),
    "fib_cluster": ("fibonacci", "both"), "higher_tf_fib": ("fibonacci", "both"),
    "higher_tf_support_zone": ("structure", "bullish"), "higher_tf_resistance_zone": ("structure", "bearish"),
    "higher_tf_support_trendline": ("structure", "bullish"), "higher_tf_resistance_trendline": ("structure", "bearish"),
    "support_zone": ("structure", "bullish"), "resistance_zone": ("structure", "bearish"),
    "support_trendline": ("structure", "bullish"), "resistance_trendline": ("structure", "bearish"),
    "pivot_point": ("structure", "both"), "round_level": ("structure", "both"),
    "volume_spike": ("volume", "both"), "volume_dryup": ("volume", "both"), "volume_profile": ("volume", "both"),
    "macd_bullish_crossover": ("volume", "bullish"), "macd_bearish_crossover": ("volume", "bearish"),
    "macd_histogram_reversal": ("volume", "both"),
    "macd_bullish_divergence": ("volume", "bullish"), "macd_bearish_divergence": ("volume", "bearish"),
    "obv_bullish_divergence": ("volume", "bullish"), "obv_bearish_divergence": ("volume", "bearish"),
}
CATEGORIES = ("momentum", "candles", "fibonacci", "structure", "volume")
# Konfluencje poziomowe - znane, zanim cena dojdzie do PRZ (siła wstępna setupu "waiting").
# Pozostałe (świece, RSI/stochastic, dywergencje, wolumen, MACD) to reakcja ceny w strefie.
LEVEL_TYPES = frozenset(t for t, (cat, _) in CONFLUENCE_CATALOG.items() if cat in ("fibonacci", "structure")) | {
    "volume_profile"}
KINDS = ("entry", "pre")   # siła pełna (od wejścia) i wstępna (setup czeka na PRZ)
CATEGORY_LABELS = {"momentum": "RSI / Stochastic", "candles": "świece", "fibonacci": "Fibonacci",
                   "structure": "S/R / trendline", "volume": "wolumen / MACD / OBV"}

MODEL_VERSION = 1
L2 = 2.0                 # siła regularyzacji (na cechę)
MIN_FEATURE_COUNT = 30   # cechy rzadsze w danych uczących pomijamy (szum)
TRAIN_SHARE = 0.7
DECIDED = ("win", "loss", "expired")


# ─────────────────────────── cechy ───────────────────────────

def _alignment(direction: str, is_bullish: bool) -> str:
    if direction == "both":
        return "neutral"
    return "with" if (direction == "bullish") == bool(is_bullish) else "against"


def ratio_deviation(points: Dict[str, Tuple[int, float]], pattern_type: str) -> Optional[float]:
    """Odchylenie proporcji X..D od definicji formacji (0 = w zakresach); None bez X albo D."""
    if not all(k in points for k in ("X", "A", "B", "C", "D")):
        return None
    try:
        result = validate_xabcd({k: Point(time=int(t), price=float(p)) for k, (t, p) in points.items()})
    except (ValidationError, ValueError, TypeError):
        return None
    for cand in result["candidates"]:
        if cand["pattern"] == pattern_type:
            return float(cand["deviation"])
    return None


def features(pattern_type: str, is_bullish: bool, interval: Optional[str], spacing: Optional[float],
             confluences: Iterable[Dict[str, Any]], deviation: Optional[float]) -> Dict[str, float]:
    f: Dict[str, float] = {f"pattern:{pattern_type}": 1.0}
    if interval:
        f[f"interval:{interval}"] = 1.0
    if spacing:
        f["structure_size"] = math.log(max(1.0, float(spacing))) / math.log(30.0)
    if deviation is not None:
        f["ratio_deviation"] = min(1.0, max(0.0, deviation))
    with_count = against_count = 0
    covered = set()
    for c in confluences or []:
        ctype = c.get("type") if isinstance(c, dict) else None
        if not ctype:
            continue
        category, direction = CONFLUENCE_CATALOG.get(ctype, ("other", "both"))
        align = _alignment(direction, is_bullish)
        f[f"conf:{ctype}:{align}"] = 1.0
        if align == "with":
            with_count += 1
            covered.add(category)
        elif align == "against":
            against_count += 1
        else:
            covered.add(category)
    f["confluences_with"] = min(with_count, 8) / 8.0
    f["confluences_against"] = min(against_count, 8) / 8.0
    for cat in covered:
        if cat in CATEGORIES:
            f[f"category:{cat}"] = 1.0
    return f


def _confluence_list(confluences_json: Any) -> List[Dict[str, Any]]:
    if isinstance(confluences_json, dict):
        return list(confluences_json.get("confluences") or [])
    return []


def setup_features(row: Dict[str, Any], kind: str = "entry") -> Dict[str, float]:
    """Wiersz technical_analysis_harmonic_setups -> cechy.

    kind="entry": D = wejście, wszystkie konfluencje z chwili wejścia.
    kind="pre":   tylko konfluencje poziomowe (LEVEL_TYPES). Dla setupu z wejściem - podzbiór
                  konfluencji z wejścia (tak uczymy model wstępny); dla czekającego - pre_confluences_json
                  liczone na bliższej krawędzi PRZ, D = ta krawędź.
    """
    pts = row.get("points_json") or {}
    points = {k: (v["time"], v["price"]) for k, v in pts.items() if isinstance(v, dict)}
    if row.get("entry_time") is not None and row.get("entry_price") is not None:
        points["D"] = (row["entry_time"], row["entry_price"])
        confluences = _confluence_list(row.get("confluences_json"))
    else:
        near_edge = row.get("prz_max") if row.get("is_bullish") else row.get("prz_min")
        if near_edge is not None and row.get("created_time") is not None:
            points["D"] = (row["created_time"], near_edge)
        confluences = _confluence_list(row.get("pre_confluences_json"))
    if kind == "pre":
        confluences = [c for c in confluences if isinstance(c, dict) and c.get("type") in LEVEL_TYPES]
    return features(row["pattern_type"], row["is_bullish"], row.get("interval"), row.get("spacing"),
                    confluences, ratio_deviation(points, row["pattern_type"]))


def pattern_features(row: Dict[str, Any]) -> Dict[str, float]:
    """Wiersz technical_analysis_harmonic_patterns (to, co pokazuje sidebar) -> cechy."""
    ta = row.get("ta_object_json") or {}
    pattern_type = ta.get("pattern_type") or ""
    points = {}
    for name, p in (ta.get("points") or {}).items():
        if isinstance(p, dict) and p.get("price") is not None:
            t = p.get("timestamp") or p.get("open_time") or row.get(f"{name.lower()}_point_timestamp")
            if t is not None:
                points[name] = (t, p["price"])
    return features(pattern_type, bool(ta.get("is_bullish", True)), row.get("interval"), ta.get("peak_spacing"),
                    _confluence_list(row.get("confluences_json")), ratio_deviation(points, pattern_type))


# ─────────────────────────── model ───────────────────────────

@dataclass
class StrengthModel:
    feature_names: List[str]
    weights: List[float]
    intercept: float
    quantiles: List[float]                 # 101 punktów rozkładu logitu na danych uczących
    metrics: Dict[str, Any] = field(default_factory=dict)
    trained_at: str = ""
    params_version: str = ""
    model_version: int = MODEL_VERSION
    kind: str = "entry"

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StrengthModel":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})

    def logit(self, f: Dict[str, float]) -> float:
        return self.intercept + sum(w * f.get(n, 0.0) for n, w in zip(self.feature_names, self.weights))

    def score(self, f: Dict[str, float], top: int = 3) -> Dict[str, Any]:
        z = self.logit(f)
        q = np.asarray(self.quantiles)
        pct = int(round(float(np.searchsorted(q, z, side="right")) / len(q) * 100))
        contributions = sorted(
            ((n, w * f.get(n, 0.0)) for n, w in zip(self.feature_names, self.weights) if f.get(n)),
            key=lambda kv: -abs(kv[1]),
        )[:top]
        return {
            "score": max(0, min(100, pct)),
            "p_win": round(1.0 / (1.0 + math.exp(-z)), 4),
            "factors": [{"feature": n, "label": feature_label(n), "impact": round(v, 3)} for n, v in contributions],
            "model_trained_at": self.trained_at,
            "kind": self.kind,
        }


def feature_label(name: str) -> str:
    kind, _, rest = name.partition(":")
    if kind == "conf":
        ctype, _, align = rest.rpartition(":")
        suffix = {"with": "zgodna z kierunkiem", "against": "przeciw kierunkowi", "neutral": ""}.get(align, align)
        return f"{ctype.replace('_', ' ')}" + (f" ({suffix})" if suffix else "")
    if kind == "category":
        return f"kategoria: {CATEGORY_LABELS.get(rest, rest)}"
    if kind == "pattern":
        return f"formacja {rest}"
    if kind == "interval":
        return f"interwał {rest}"
    return {"structure_size": "wielkość struktury", "ratio_deviation": "odchylenie proporcji",
            "confluences_with": "liczba konfluencji zgodnych", "confluences_against": "liczba konfluencji przeciwnych"
            }.get(name, name)


def _fit_logistic(X: np.ndarray, y: np.ndarray, l2: float = L2, iterations: int = 25) -> Tuple[np.ndarray, float]:
    """IRLS (Newton) z L2 na wagach (bez wyrazu wolnego)."""
    n, k = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    beta = np.zeros(k + 1)
    beta[0] = math.log(max(y.mean(), 1e-6) / max(1 - y.mean(), 1e-6))
    reg = np.eye(k + 1) * l2
    reg[0, 0] = 0.0
    for _ in range(iterations):
        p = 1.0 / (1.0 + np.exp(-(Xb @ beta)))
        w = p * (1 - p) + 1e-9
        grad = Xb.T @ (y - p) - reg @ beta
        hess = (Xb * w[:, None]).T @ Xb + reg
        step = np.linalg.solve(hess, grad)
        beta += step
        if np.max(np.abs(step)) < 1e-6:
            break
    return beta[1:], float(beta[0])


def _auc(scores: np.ndarray, y: np.ndarray) -> Optional[float]:
    pos, neg = scores[y == 1], scores[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return None
    order = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
    ranks = np.empty(len(order))
    ranks[order] = np.arange(1, len(order) + 1)
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def _quintiles(scores: np.ndarray, y: np.ndarray, r: np.ndarray) -> List[Dict[str, Any]]:
    if len(scores) < 10:
        return []
    order = np.argsort(scores)
    out = []
    for i, chunk in enumerate(np.array_split(order, 5)):
        out.append({"quintile": i + 1, "n": int(len(chunk)), "win_rate": round(float(y[chunk].mean()), 4),
                    "avg_r": round(float(r[chunk].mean()), 4)})
    return out


def _matrix(samples: Sequence[Dict[str, float]], names: List[str]) -> np.ndarray:
    index = {n: i for i, n in enumerate(names)}
    X = np.zeros((len(samples), len(names)))
    for row, f in enumerate(samples):
        for n, v in f.items():
            if n in index:
                X[row, index[n]] = v
    return X


def fit(samples: Sequence[Tuple[Dict[str, float], int, float, int]], params_version: str = "",
        kind: str = "entry") -> StrengthModel:
    """samples: (cechy, 1 = TP1 przed SL, R transakcji, czas wejścia ms). Zwraca model produkcyjny
    (uczony na całości) z metrykami z walidacji na najnowszych (1 - TRAIN_SHARE) setupach."""
    if len(samples) < 200:
        raise ValueError(f"za mało rozstrzygniętych setupów do uczenia ({len(samples)} < 200)")
    samples = sorted(samples, key=lambda s: s[3])
    cut = int(len(samples) * TRAIN_SHARE)
    train, test = samples[:cut], samples[cut:]

    def names_for(rows):
        counts: Dict[str, int] = {}
        for f, *_ in rows:
            for n, v in f.items():
                if v:
                    counts[n] = counts.get(n, 0) + 1
        return sorted(n for n, c in counts.items() if c >= MIN_FEATURE_COUNT)

    names = names_for(train)
    w, b = _fit_logistic(_matrix([s[0] for s in train], names), np.array([s[1] for s in train], dtype=float))
    X_test = _matrix([s[0] for s in test], names)
    y_test = np.array([s[1] for s in test], dtype=float)
    r_test = np.array([s[2] for s in test], dtype=float)
    z_test = b + X_test @ w
    metrics = {
        "samples": len(samples), "train": len(train), "test": len(test),
        "test_from": datetime.fromtimestamp(test[0][3] / 1000, tz=timezone.utc).isoformat() if test else None,
        "base_win_rate_test": round(float(y_test.mean()), 4) if len(test) else None,
        "auc_test": _auc(z_test, y_test),
        "quintiles_test": _quintiles(z_test, y_test, r_test),
    }

    names = names_for(samples)
    X = _matrix([s[0] for s in samples], names)
    w, b = _fit_logistic(X, np.array([s[1] for s in samples], dtype=float))
    z = b + X @ w
    quantiles = [float(v) for v in np.quantile(z, np.linspace(0, 1, 101))]
    return StrengthModel(feature_names=names, weights=[round(float(v), 6) for v in w], intercept=round(b, 6),
                         quantiles=quantiles, metrics=metrics, params_version=params_version, kind=kind,
                         trained_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))


def training_samples(rows: Iterable[Dict[str, Any]], kind: str = "entry") -> List[Tuple[Dict[str, float], int, float, int]]:
    out = []
    for r in rows:
        if r.get("status") not in DECIDED or r.get("entry_time") is None:
            continue
        out.append((setup_features(r, kind), 1 if r["status"] == "win" else 0, float(r.get("r_multiple") or 0.0),
                    int(r["entry_time"])))
    return out


def top_weights(model: StrengthModel, n: int = 15) -> List[Dict[str, Any]]:
    pairs = sorted(zip(model.feature_names, model.weights), key=lambda kv: -abs(kv[1]))[:n]
    return [{"feature": f, "label": feature_label(f), "weight": round(w, 4)} for f, w in pairs]


def fit_before(samples: Sequence[Tuple[Dict[str, float], int, float, int]], cutoff_ms: int,
               kind: str = "entry") -> StrengthModel:
    """Model uczony WYŁĄCZNIE na setupach z wejściem przed cutoff_ms - do oceny filtrów siły na
    danych późniejszych bez przecieku (model produkcyjny z fit() widział całość)."""
    train = [s for s in samples if s[3] < cutoff_ms]
    if len(train) < 200:
        raise ValueError(f"za mało setupów przed {cutoff_ms} ({len(train)} < 200)")
    counts: Dict[str, int] = {}
    for f, *_ in train:
        for n, v in f.items():
            if v:
                counts[n] = counts.get(n, 0) + 1
    names = sorted(n for n, c in counts.items() if c >= MIN_FEATURE_COUNT)
    X = _matrix([s[0] for s in train], names)
    w, b = _fit_logistic(X, np.array([s[1] for s in train], dtype=float))
    z = b + X @ w
    return StrengthModel(feature_names=names, weights=[float(v) for v in w], intercept=b,
                         quantiles=[float(v) for v in np.quantile(z, np.linspace(0, 1, 101))],
                         metrics={"train": len(train), "cutoff_ms": cutoff_ms}, kind=kind,
                         trained_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
