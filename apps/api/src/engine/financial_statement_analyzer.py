from typing import Any, Dict


class FinancialStatementAnalyzer:
    """Cookbook-inspired ratio calculation and interpretation engine."""

    BENCHMARKS = {
        "technology": {
            "current_ratio": {"excellent": 2.5, "good": 1.8, "acceptable": 1.2},
            "debt_to_equity": {"excellent": 0.3, "good": 0.5, "acceptable": 1.0},
            "roe": {"excellent": 0.25, "good": 0.18, "acceptable": 0.12},
            "operating_margin": {"excellent": 0.25, "good": 0.18, "acceptable": 0.12},
        },
        "manufacturing": {
            "current_ratio": {"excellent": 2.2, "good": 1.7, "acceptable": 1.3},
            "debt_to_equity": {"excellent": 0.4, "good": 0.7, "acceptable": 1.2},
            "roe": {"excellent": 0.18, "good": 0.14, "acceptable": 0.10},
            "operating_margin": {"excellent": 0.18, "good": 0.12, "acceptable": 0.08},
        },
        "general": {
            "current_ratio": {"excellent": 2.0, "good": 1.5, "acceptable": 1.0},
            "debt_to_equity": {"excellent": 0.5, "good": 1.0, "acceptable": 1.5},
            "roe": {"excellent": 0.20, "good": 0.15, "acceptable": 0.10},
            "operating_margin": {"excellent": 0.20, "good": 0.14, "acceptable": 0.08},
        },
    }

    @staticmethod
    def _safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
        if denominator == 0:
            return default
        return numerator / denominator

    @staticmethod
    def _sector_from_industry(industry: str) -> str:
        blob = (industry or "").lower()
        if any(x in blob for x in ["tech", "software", "it", "digital"]):
            return "technology"
        if any(x in blob for x in ["manufact", "industrial", "factory", "auto"]):
            return "manufacturing"
        return "general"

    def _benchmarks_for(self, industry: str) -> Dict[str, Dict[str, float]]:
        return self.BENCHMARKS[self._sector_from_industry(industry)]

    def calculate_ratios(self, payload: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
        revenue = float(payload.get("revenue") or 0.0)
        ebitda = float(payload.get("ebitda") or 0.0)
        pat = float(payload.get("net_income") or 0.0)

        current_assets = float(payload.get("current_assets") or 0.0)
        current_liabilities = float(payload.get("current_liabilities") or 0.0)
        inventory = float(payload.get("inventory") or 0.0)

        total_debt = float(payload.get("total_debt") or 0.0)
        shareholders_equity = float(payload.get("shareholders_equity") or 0.0)
        total_assets = float(payload.get("total_assets") or 0.0)

        ratios = {
            "profitability": {
                "operating_margin": self._safe_divide(ebitda, revenue),
                "net_margin": self._safe_divide(pat, revenue),
                "roe": self._safe_divide(pat, shareholders_equity),
                "roa": self._safe_divide(pat, total_assets),
            },
            "liquidity": {
                "current_ratio": self._safe_divide(current_assets, current_liabilities),
                "quick_ratio": self._safe_divide(current_assets - inventory, current_liabilities),
                "cash_ratio": self._safe_divide(float(payload.get("cash_and_equivalents") or 0.0), current_liabilities),
            },
            "leverage": {
                "debt_to_equity": self._safe_divide(total_debt, shareholders_equity),
                "interest_coverage": self._safe_divide(float(payload.get("ebit") or 0.0), float(payload.get("interest_expense") or 0.0)),
            },
            "efficiency": {
                "asset_turnover": self._safe_divide(revenue, total_assets),
                "receivables_turnover": self._safe_divide(revenue, float(payload.get("accounts_receivable") or 0.0)),
            },
        }
        return ratios

    def _rate_higher_better(self, value: float, bm: Dict[str, float]) -> str:
        if value >= bm["excellent"]:
            return "Excellent"
        if value >= bm["good"]:
            return "Good"
        if value >= bm["acceptable"]:
            return "Acceptable"
        return "Poor"

    def _rate_lower_better(self, value: float, bm: Dict[str, float]) -> str:
        if value <= bm["excellent"]:
            return "Excellent"
        if value <= bm["good"]:
            return "Good"
        if value <= bm["acceptable"]:
            return "Acceptable"
        return "Poor"

    def interpret(self, ratios: Dict[str, Dict[str, float]], industry: str) -> Dict[str, Any]:
        bm = self._benchmarks_for(industry)
        interpreted = {"current_analysis": {}, "recommendations": []}

        mapping = {
            "current_ratio": ("liquidity", "higher"),
            "debt_to_equity": ("leverage", "lower"),
            "roe": ("profitability", "higher"),
            "operating_margin": ("profitability", "higher"),
        }

        score_map = {"Excellent": 4, "Good": 3, "Acceptable": 2, "Poor": 1}
        scores = []

        for ratio_name, (category, direction) in mapping.items():
            value = float(ratios.get(category, {}).get(ratio_name, 0.0))
            if ratio_name not in bm:
                continue
            rating = (
                self._rate_higher_better(value, bm[ratio_name])
                if direction == "higher"
                else self._rate_lower_better(value, bm[ratio_name])
            )
            scores.append(score_map.get(rating, 2))
            interpreted["current_analysis"][ratio_name] = {
                "value": value,
                "rating": rating,
                "benchmark": bm[ratio_name],
            }
            if rating == "Poor":
                interpreted["recommendations"].append(
                    f"Priority: Improve {ratio_name.replace('_', ' ')} to align with sector benchmarks"
                )

        avg_score = (sum(scores) / len(scores)) if scores else 2.0
        if avg_score >= 3.5:
            health = "Excellent"
        elif avg_score >= 2.5:
            health = "Good"
        elif avg_score >= 1.5:
            health = "Fair"
        else:
            health = "Poor"

        interpreted["overall_health"] = {
            "status": health,
            "score": round(avg_score, 2),
            "message": "Company shows strong financial health"
            if health == "Excellent"
            else "Overall healthy with improvement opportunities"
            if health == "Good"
            else "Mixed indicators; requires targeted action"
            if health == "Fair"
            else "Significant financial stress signals",
        }

        if not interpreted["recommendations"]:
            interpreted["recommendations"] = [
                "Continue current financial management practices",
                "Monitor leverage and liquidity trend quarterly",
            ]

        return interpreted

    @staticmethod
    def _trend_label(first: float, last: float, higher_is_better: bool, threshold: float = 0.03) -> str:
        if first == 0:
            delta = 0.0 if last == 0 else 1.0
        else:
            delta = (last - first) / abs(first)
        if abs(delta) <= threshold:
            return "Stable"
        improved = delta > 0 if higher_is_better else delta < 0
        return "Improving" if improved else "Deteriorating"

    def _analyze_trends(self, payload: Dict[str, Any], industry: str) -> Dict[str, Any]:
        periods = payload.get("historical_periods")
        if not isinstance(periods, list) or len(periods) < 2:
            return {
                "signal": "Insufficient Data",
                "metrics": {},
                "period_count": len(periods) if isinstance(periods, list) else 0,
            }

        series = {
            "current_ratio": [],
            "debt_to_equity": [],
            "roe": [],
            "operating_margin": [],
        }

        for period in periods:
            if not isinstance(period, dict):
                continue
            ratios = self.calculate_ratios(period)
            series["current_ratio"].append(float(ratios.get("liquidity", {}).get("current_ratio", 0.0)))
            series["debt_to_equity"].append(float(ratios.get("leverage", {}).get("debt_to_equity", 0.0)))
            series["roe"].append(float(ratios.get("profitability", {}).get("roe", 0.0)))
            series["operating_margin"].append(float(ratios.get("profitability", {}).get("operating_margin", 0.0)))

        metric_rules = {
            "current_ratio": True,
            "debt_to_equity": False,
            "roe": True,
            "operating_margin": True,
        }
        score_map = {"Improving": 1, "Stable": 0, "Deteriorating": -1}
        metric_signals = {}
        trend_score = 0
        for metric_name, higher_is_better in metric_rules.items():
            metric_series = series.get(metric_name, [])
            if len(metric_series) < 2:
                continue
            signal = self._trend_label(metric_series[0], metric_series[-1], higher_is_better)
            trend_score += score_map[signal]
            metric_signals[metric_name] = {
                "signal": signal,
                "start": round(metric_series[0], 4),
                "end": round(metric_series[-1], 4),
                "series": [round(v, 4) for v in metric_series],
            }

        if trend_score >= 2:
            overall_signal = "Improving"
        elif trend_score <= -2:
            overall_signal = "Deteriorating"
        else:
            overall_signal = "Stable"

        return {
            "signal": overall_signal,
            "score": trend_score,
            "industry_context": self._sector_from_industry(industry),
            "metrics": metric_signals,
            "period_count": len(periods),
        }

    def analyze(self, payload: Dict[str, Any], industry: str) -> Dict[str, Any]:
        ratios = self.calculate_ratios(payload)
        interpreted = self.interpret(ratios, industry)
        return {
            "industry_context": self._sector_from_industry(industry),
            "ratios": ratios,
            "analysis": interpreted,
            "trend_analysis": self._analyze_trends(payload, industry),
        }
