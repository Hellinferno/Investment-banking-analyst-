"""Quick integration test for the deterministic triangulator."""
import sys

sys.path.insert(0, ".")

from engine.triangulator import Triangulator


data_clean = {
    "total_borrowings": 5_000_000_000,
    "cash_and_equivalents": 2_000_000_000,
    "net_debt": 3_000_000_000,
    "historical_revenues": [20_000_000_000, 22_000_000_000, 25_000_000_000],
    "historical_ebitda_margins": [0.12, 0.13, 0.14],
    "shares_outstanding": 500_000_000,
    "debt_to_equity": 0.5,
}

result = Triangulator.run_all_checks(data_clean)
print(f"Test 1 (clean data): {result['overall_verdict'].upper()}")
print(f"  Passed: {result['passed']}/{result['total_checks']}")
for check in result["results"]:
    status = "PASS" if check["passed"] else "FAIL"
    print(f"  {status} | {check['identity']}")

data_bad = dict(data_clean)
data_bad["net_debt"] = 10_000_000_000

result_bad = Triangulator.run_all_checks(data_bad)
print(f"\nTest 2 (bad net debt): {result_bad['overall_verdict'].upper()}")
for check in result_bad["results"]:
    status = "PASS" if check["passed"] else "FAIL"
    print(f"  {status} | {check['identity']} | dev={check['deviation_pct']:.1f}%")

print("\nAll tests completed.")
