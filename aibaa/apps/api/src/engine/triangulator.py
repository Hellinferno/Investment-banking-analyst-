"""
Deterministic accounting triangulation checks.

These checks validate extracted facts before they reach the DCF engine.
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass


@dataclass
class TriangulationResult:
    identity_name: str
    passed: bool
    expected: float
    actual: float
    deviation_pct: float
    details: str
    severity: str = "info"


class Triangulator:
    TOLERANCE = 0.05

    @classmethod
    def run_all_checks(cls, data: dict) -> Dict[str, Any]:
        results: List[TriangulationResult] = []

        for check in (
            cls.check_net_debt_identity,
            cls.check_ebitda_reconciliation,
            cls.check_revenue_margin_crosscheck,
            cls.check_shares_sanity,
            cls.check_de_consistency,
            cls.check_cash_flow_triangulation,
            cls.check_implied_ev_ebitda,
            cls.check_lease_liability_inclusion,
        ):
            result = check(data)
            if result:
                results.append(result)

        passed = [result for result in results if result.passed]
        failed = [result for result in results if not result.passed]
        critical = [result for result in failed if result.severity == "critical"]

        overall = "pass"
        if critical:
            overall = "halt"
        elif failed:
            overall = "warning"

        return {
            "overall_verdict": overall,
            "total_checks": len(results),
            "passed": len(passed),
            "failed": len(failed),
            "critical_failures": len(critical),
            "results": [
                {
                    "identity": result.identity_name,
                    "passed": result.passed,
                    "expected": round(result.expected, 2),
                    "actual": round(result.actual, 2),
                    "deviation_pct": round(result.deviation_pct, 2),
                    "details": result.details,
                    "severity": result.severity,
                }
                for result in results
            ],
        }

    @classmethod
    def check_net_debt_identity(cls, data: dict) -> Optional[TriangulationResult]:
        borrowings = data.get("total_borrowings")
        lease_liabilities = data.get("lease_liabilities", 0)
        cash = data.get("cash_and_equivalents")
        net_debt = data.get("net_debt")

        if borrowings is None or cash is None or net_debt is None:
            return None

        try:
            borrowings = float(borrowings)
            lease_liabilities = float(lease_liabilities or 0)
            cash = float(cash)
            net_debt = float(net_debt)
        except (ValueError, TypeError):
            return None

        expected = borrowings + lease_liabilities - cash
        deviation = abs(expected - net_debt) / max(abs(expected), 1)

        return TriangulationResult(
            identity_name="Net Debt = Borrowings + Leases - Cash",
            passed=deviation <= cls.TOLERANCE,
            expected=expected,
            actual=net_debt,
            deviation_pct=deviation * 100,
            details=(
                f"Borrowings={borrowings:,.0f}, Leases={lease_liabilities:,.0f}, Cash={cash:,.0f}, "
                f"Expected ND={expected:,.0f}, Reported ND={net_debt:,.0f}"
            ),
            severity="critical" if deviation > 0.20 else "warning",
        )

    @classmethod
    def check_ebitda_reconciliation(cls, data: dict) -> Optional[TriangulationResult]:
        revenues = data.get("historical_revenues")
        margins = data.get("historical_ebitda_margins")

        if not revenues or not margins:
            return None
        if not isinstance(revenues, list) or not isinstance(margins, list):
            return None

        try:
            latest_rev = float(revenues[-1])
            latest_margin = float(margins[-1])
        except (ValueError, TypeError, IndexError):
            return None

        if latest_rev <= 0:
            return None

        implied_ebitda = latest_rev * latest_margin
        explicit_ebitda = data.get("latest_ebitda")

        if explicit_ebitda is not None:
            try:
                explicit_ebitda = float(explicit_ebitda)
                deviation = abs(implied_ebitda - explicit_ebitda) / max(abs(explicit_ebitda), 1)
                return TriangulationResult(
                    identity_name="EBITDA = Revenue x Margin",
                    passed=deviation <= cls.TOLERANCE,
                    expected=implied_ebitda,
                    actual=explicit_ebitda,
                    deviation_pct=deviation * 100,
                    details=(
                        f"Rev={latest_rev:,.0f}, Margin={latest_margin:.2%}, "
                        f"Implied EBITDA={implied_ebitda:,.0f}, Reported EBITDA={explicit_ebitda:,.0f}"
                    ),
                    severity="warning",
                )
            except (ValueError, TypeError):
                pass

        margin_ok = -1.0 <= latest_margin <= 0.80
        return TriangulationResult(
            identity_name="EBITDA Margin Range Check",
            passed=margin_ok,
            expected=0.0,
            actual=latest_margin,
            deviation_pct=0.0 if margin_ok else abs(latest_margin) * 100,
            details=f"Margin={latest_margin:.2%}, {'within' if margin_ok else 'outside'} [-100%, +80%] range",
            severity="info" if margin_ok else "warning",
        )

    @classmethod
    def check_revenue_margin_crosscheck(cls, data: dict) -> Optional[TriangulationResult]:
        revenues = data.get("historical_revenues", [])
        margins = data.get("historical_ebitda_margins", [])

        if not revenues or not margins:
            return None

        matched = len(revenues) == len(margins)
        return TriangulationResult(
            identity_name="Revenue-Margin Array Length Match",
            passed=matched,
            expected=float(len(revenues)),
            actual=float(len(margins)),
            deviation_pct=0.0 if matched else abs(len(revenues) - len(margins)) / max(len(revenues), 1) * 100,
            details=f"Revenues: {len(revenues)} years, Margins: {len(margins)} years",
            severity="critical" if not matched else "info",
        )

    @classmethod
    def check_shares_sanity(cls, data: dict) -> Optional[TriangulationResult]:
        shares = data.get("shares_outstanding")
        if shares is None:
            return None

        try:
            shares = float(shares)
        except (ValueError, TypeError):
            return None

        min_shares = 4_200_000
        max_shares = 6_400_000_000
        in_range = min_shares <= shares <= max_shares

        return TriangulationResult(
            identity_name="Shares Outstanding Range Check",
            passed=in_range,
            expected=(min_shares + max_shares) / 2,
            actual=shares,
            deviation_pct=0.0 if in_range else 100.0,
            details=f"Shares={shares:,.0f}, Range=[{min_shares:,.0f}, {max_shares:,.0f}]",
            severity="critical" if not in_range else "info",
        )

    @classmethod
    def check_de_consistency(cls, data: dict) -> Optional[TriangulationResult]:
        borrowings = data.get("total_borrowings")
        lease_liabilities = data.get("lease_liabilities", 0)
        debt_to_equity = data.get("debt_to_equity")

        if borrowings is None or debt_to_equity is None:
            return None

        try:
            borrowings = float(borrowings)
            lease_liabilities = float(lease_liabilities or 0)
            debt_to_equity = float(debt_to_equity)
        except (ValueError, TypeError):
            return None

        total_debt = borrowings + lease_liabilities
        if total_debt <= 0 and debt_to_equity > 0:
            return TriangulationResult(
                identity_name="D/E Consistency (Zero Debt)",
                passed=False,
                expected=0.0,
                actual=debt_to_equity,
                deviation_pct=100.0,
                details=f"Total debt={total_debt:,.0f} but D/E={debt_to_equity:.2f}; should be 0.",
                severity="warning",
            )

        return TriangulationResult(
            identity_name="D/E Consistency",
            passed=True,
            expected=debt_to_equity,
            actual=debt_to_equity,
            deviation_pct=0.0,
            details=f"Total debt={total_debt:,.0f}, D/E={debt_to_equity:.2f} looks consistent.",
            severity="info",
        )

    @classmethod
    def check_cash_flow_triangulation(cls, data: dict) -> Optional[TriangulationResult]:
        net_income = data.get("net_income")
        da = data.get("depreciation_amortization")
        ocf = data.get("operating_cash_flow")

        if net_income is None or da is None or ocf is None:
            return None

        try:
            net_income = float(net_income)
            da = float(da)
            ocf = float(ocf)
        except (ValueError, TypeError):
            return None

        implied_ocf = net_income + da
        deviation = abs(implied_ocf - ocf) / max(abs(ocf), 1)

        return TriangulationResult(
            identity_name="Cash Flow Triangulation (NI + D&A ~= OCF)",
            passed=deviation <= 0.30,
            expected=implied_ocf,
            actual=ocf,
            deviation_pct=deviation * 100,
            details=f"NI={net_income:,.0f} + D&A={da:,.0f} = {implied_ocf:,.0f}, OCF={ocf:,.0f}",
            severity="warning" if deviation > 0.30 else "info",
        )

    @classmethod
    def check_implied_ev_ebitda(cls, data: dict) -> Optional[TriangulationResult]:
        enterprise_value = data.get("enterprise_value")
        terminal_ebitda = data.get("terminal_ebitda")

        if enterprise_value is None or terminal_ebitda is None:
            return None

        try:
            enterprise_value = float(enterprise_value)
            terminal_ebitda = float(terminal_ebitda)
        except (ValueError, TypeError):
            return None

        if terminal_ebitda <= 0:
            return TriangulationResult(
                identity_name="Implied EV/EBITDA Multiple",
                passed=False,
                expected=20.0,
                actual=0.0,
                deviation_pct=100.0,
                details=f"Terminal EBITDA={terminal_ebitda:,.0f} is non-positive.",
                severity="critical",
            )

        implied_multiple = enterprise_value / terminal_ebitda
        if implied_multiple < 3.0 or implied_multiple > 50.0:
            passed = False
            severity = "critical"
        elif implied_multiple < 5.0 or implied_multiple > 35.0:
            passed = False
            severity = "warning"
        else:
            passed = True
            severity = "info"

        return TriangulationResult(
            identity_name="Implied EV/EBITDA Multiple",
            passed=passed,
            expected=20.0,
            actual=implied_multiple,
            deviation_pct=abs(implied_multiple - 20.0) / 20.0 * 100,
            details=(
                f"EV={enterprise_value:,.0f}, Terminal EBITDA={terminal_ebitda:,.0f}, "
                f"Implied Multiple={implied_multiple:.1f}x"
            ),
            severity=severity,
        )

    @classmethod
    def check_lease_liability_inclusion(cls, data: dict) -> Optional[TriangulationResult]:
        lease_liabilities = data.get("lease_liabilities")
        borrowings = data.get("total_borrowings")
        cash = data.get("cash_and_equivalents")
        net_debt = data.get("net_debt")

        if lease_liabilities is None or borrowings is None or cash is None or net_debt is None:
            return None

        try:
            lease_liabilities = float(lease_liabilities)
            borrowings = float(borrowings)
            cash = float(cash)
            net_debt = float(net_debt)
        except (ValueError, TypeError):
            return None

        if lease_liabilities <= 0:
            return None

        expected = borrowings + lease_liabilities - cash
        deviation = abs(expected - net_debt) / max(abs(expected), 1)

        return TriangulationResult(
            identity_name="Net Debt includes Lease Liabilities",
            passed=deviation <= cls.TOLERANCE,
            expected=expected,
            actual=net_debt,
            deviation_pct=deviation * 100,
            details=(
                f"Borrowings={borrowings:,.0f} + Leases={lease_liabilities:,.0f} - Cash={cash:,.0f} "
                f"= Expected ND={expected:,.0f}, Actual ND={net_debt:,.0f}"
            ),
            severity="warning" if deviation > cls.TOLERANCE else "info",
        )
