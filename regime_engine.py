"""
CycleMind Regime Engine

Detects the current market regime per asset and produces a composite
confidence score from weighted, backtestable components. All four
modules (DCA, liquidation heatmap, funding capture, rebalancer) read
from this same engine so signals stay consistent across the dashboard
instead of acting as independent, disconnected tools.

Regimes (per asset):
  1. STRONG_UPTREND   — sustained directional momentum, high conviction
  2. WEAK_UPTREND     — drifting higher, low conviction / choppy
  3. RANGE_BOUND      — no clear direction, mean-reverting
  4. WEAK_DOWNTREND   — drifting lower, low conviction / choppy
  5. STRONG_DOWNTREND — sustained directional momentum, high conviction

Composite confidence score components (weighted):
  - Volume Divergence Score   (25%) — price/volume relationship strength
  - BTC Dominance Momentum    (20%) — BTC.D trend, only meaningfully
                                       affects ETH/SOL scoring
  - Indicator Agreement       (30%) — RSI, MACD, EMA alignment
  - Funding Rate Alignment    (25%) — does funding rate confirm or
                                       contradict the detected direction
"""

from dataclasses import dataclass
from enum import Enum


class Regime(str, Enum):
    STRONG_UPTREND = "strong_uptrend"
    WEAK_UPTREND = "weak_uptrend"
    RANGE_BOUND = "range_bound"
    WEAK_DOWNTREND = "weak_downtrend"
    STRONG_DOWNTREND = "strong_downtrend"


# Confidence threshold required before CycleMind will size a position
# meaningfully for each asset. SOL is more volatile, so it requires a
# higher confidence bar before sizing up.
ASSET_CONFIDENCE_THRESHOLDS = {
    "BTCUSDT": 60,
    "ETHUSDT": 62,
    "SOLUSDT": 68,
}

COMPONENT_WEIGHTS = {
    "volume_divergence": 0.25,
    "btc_dominance_momentum": 0.20,
    "indicator_agreement": 0.30,
    "funding_alignment": 0.25,
}


@dataclass
class RegimeResult:
    symbol: str
    regime: Regime
    confidence: float
    threshold: float
    meets_threshold: bool
    components: dict


def _score_volume_divergence(candles: list[dict]) -> float:
    """
    Compares price direction vs. volume trend over the recent window.
    Rising price + rising volume (or falling price + rising volume on
    the down leg) = confirmation, scored higher. Price moving on
    declining volume = weak conviction, scored lower.
    Returns 0-100.
    """
    if len(candles) < 10:
        return 50.0  # neutral default when not enough data

    closes = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]

    price_change = closes[-1] - closes[0]
    recent_vol_avg = sum(volumes[-5:]) / 5
    earlier_vol_avg = sum(volumes[:5]) / 5
    vol_trend = recent_vol_avg - earlier_vol_avg

    if price_change == 0:
        return 50.0

    # Volume confirming the move in either direction = high score
    confirming = (price_change > 0 and vol_trend > 0) or (price_change < 0 and vol_trend > 0)
    if confirming:
        magnitude = min(abs(vol_trend) / max(earlier_vol_avg, 1e-9), 1.0)
        return 60 + (magnitude * 40)  # 60-100
    else:
        magnitude = min(abs(vol_trend) / max(earlier_vol_avg, 1e-9), 1.0)
        return 50 - (magnitude * 30)  # 20-50


def _score_btc_dominance_momentum(symbol: str, btc_dominance_change_pct: float) -> float:
    """
    BTC dominance rising = capital rotating into BTC, away from alts.
    This matters for ETH/SOL confidence (a falling-dominance environment
    supports altcoin uptrend confidence) but is mostly neutral for BTC
    itself. Returns 0-100.
    """
    if symbol == "BTCUSDT":
        return 50.0  # not a meaningful signal for BTC itself

    # For ETH/SOL: falling BTC dominance supports altcoin strength
    if btc_dominance_change_pct < -0.5:
        return 75.0
    elif btc_dominance_change_pct < 0:
        return 60.0
    elif btc_dominance_change_pct < 0.5:
        return 45.0
    else:
        return 25.0


def _score_indicator_agreement(rsi: float, macd_histogram: float, price: float, ema_50: float) -> float:
    """
    Checks whether RSI, MACD, and EMA positioning agree on direction.
    More agreement = higher confidence. Returns 0-100.
    """
    signals = []

    # RSI: >55 bullish lean, <45 bearish lean, between = neutral
    if rsi > 55:
        signals.append(1)
    elif rsi < 45:
        signals.append(-1)
    else:
        signals.append(0)

    # MACD histogram: positive = bullish momentum, negative = bearish
    if macd_histogram > 0:
        signals.append(1)
    elif macd_histogram < 0:
        signals.append(-1)
    else:
        signals.append(0)

    # Price vs EMA50: above = bullish structure, below = bearish
    if price > ema_50:
        signals.append(1)
    elif price < ema_50:
        signals.append(-1)
    else:
        signals.append(0)

    agreement = abs(sum(signals))  # 0 = total disagreement, 3 = full agreement
    return (agreement / 3) * 100


def _score_funding_alignment(funding_rate: float, direction: int) -> float:
    """
    direction: 1 for bullish bias, -1 for bearish bias, 0 for neutral.
    Positive funding in an uptrend is normal (longs paying a premium) —
    mild confirmation. Negative funding in an uptrend is a contrarian
    bullish signal (shorts crowded, paying longs) — scored highest.
    Returns 0-100.
    """
    if direction == 0:
        return 50.0

    if direction == 1:  # bullish bias
        if funding_rate < -0.0002:
            return 85.0  # shorts crowded against an uptrend = strong confirmation
        elif funding_rate < 0.0003:
            return 65.0
        elif funding_rate < 0.0008:
            return 50.0
        else:
            return 30.0  # longs overcrowded, uptrend may be exhausted
    else:  # bearish bias
        if funding_rate > 0.0002:
            return 85.0  # longs crowded against a downtrend = strong confirmation
        elif funding_rate > -0.0003:
            return 65.0
        elif funding_rate > -0.0008:
            return 50.0
        else:
            return 30.0  # shorts overcrowded, downtrend may be exhausted


def _classify_regime(price_change_pct: float, indicator_score: float, direction: int) -> Regime:
    """
    Combines magnitude of recent price movement with indicator agreement
    strength to classify the regime bucket.
    """
    if direction == 0 or abs(price_change_pct) < 1.5:
        return Regime.RANGE_BOUND

    strong = indicator_score >= 66.7 and abs(price_change_pct) >= 4.0

    if direction == 1:
        return Regime.STRONG_UPTREND if strong else Regime.WEAK_UPTREND
    else:
        return Regime.STRONG_DOWNTREND if strong else Regime.WEAK_DOWNTREND


def compute_regime(
    symbol: str,
    candles: list[dict],
    rsi: float,
    macd_histogram: float,
    ema_50: float,
    funding_rate: float,
    btc_dominance_change_pct: float = 0.0,
) -> RegimeResult:
    """
    Main entry point. Pulls together all four weighted components into
    a single composite confidence score and regime classification.

    candles: list of dicts with at least {"close": float, "volume": float},
             ordered oldest -> newest.
    """
    if not candles:
        raise ValueError("compute_regime requires at least one candle")

    current_price = candles[-1]["close"]
    price_change_pct = ((current_price - candles[0]["close"]) / candles[0]["close"]) * 100

    direction = 1 if price_change_pct > 0.3 else (-1 if price_change_pct < -0.3 else 0)

    vol_div_score = _score_volume_divergence(candles)
    btc_dom_score = _score_btc_dominance_momentum(symbol, btc_dominance_change_pct)
    indicator_score = _score_indicator_agreement(rsi, macd_histogram, current_price, ema_50)
    funding_score = _score_funding_alignment(funding_rate, direction)

    composite = (
        vol_div_score * COMPONENT_WEIGHTS["volume_divergence"]
        + btc_dom_score * COMPONENT_WEIGHTS["btc_dominance_momentum"]
        + indicator_score * COMPONENT_WEIGHTS["indicator_agreement"]
        + funding_score * COMPONENT_WEIGHTS["funding_alignment"]
    )

    regime = _classify_regime(price_change_pct, indicator_score, direction)
    threshold = ASSET_CONFIDENCE_THRESHOLDS.get(symbol, 65)

    return RegimeResult(
        symbol=symbol,
        regime=regime,
        confidence=round(composite, 1),
        threshold=threshold,
        meets_threshold=composite >= threshold,
        components={
            "volume_divergence": round(vol_div_score, 1),
            "btc_dominance_momentum": round(btc_dom_score, 1),
            "indicator_agreement": round(indicator_score, 1),
            "funding_alignment": round(funding_score, 1),
            "price_change_pct": round(price_change_pct, 2),
        },
    )


def integrate_liquidation_proximity(regime_result: RegimeResult, mark_price: float, clusters: list[dict]) -> dict:
    """
    Adjusts position-sizing guidance based on how close current price sits
    to a major liquidation cluster. Proximity to a cluster increases the
    chance of a volatility spike (cascade), so CycleMind recommends
    tightening stops or reducing size even when regime confidence is high.
    """
    closest_distance_pct = None
    closest_leverage = None

    for cluster in clusters:
        for side in ("long_liquidation_price", "short_liquidation_price"):
            cluster_price = cluster[side]
            distance_pct = abs(mark_price - cluster_price) / mark_price * 100
            if closest_distance_pct is None or distance_pct < closest_distance_pct:
                closest_distance_pct = distance_pct
                closest_leverage = cluster["leverage"]

    proximity_warning = closest_distance_pct is not None and closest_distance_pct < 2.0

    sizing_adjustment = 1.0
    if proximity_warning:
        # Within 2% of a major liquidation cluster — reduce suggested size
        sizing_adjustment = 0.5
    elif closest_distance_pct is not None and closest_distance_pct < 4.0:
        sizing_adjustment = 0.75

    return {
        "closest_cluster_distance_pct": round(closest_distance_pct, 2) if closest_distance_pct else None,
        "closest_cluster_leverage": closest_leverage,
        "cascade_risk_warning": proximity_warning,
        "position_sizing_multiplier": sizing_adjustment,
        "adjusted_confidence": round(regime_result.confidence * sizing_adjustment, 1) if proximity_warning else regime_result.confidence,
    }
