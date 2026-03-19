import sys
sys.path.insert(0, 'src')

from engine.dcf import DCFEngine
from tools.excel_writer import WorkbookBuilder

# Test with sample data
engine = DCFEngine(
    historical_revenues=[250000000000, 250000000000, 250000000000],
    historical_ebitda_margins=[0.12, 0.12, 0.12],
    dso=45.0,
    dpo=30.0,
    dio=30.0
)

print("Building projections...")
projections = engine.build_projections(projection_years=7, terminal_growth_rate=0.025, scenario='base')
print("Projections built successfully")
print("Assumptions keys:", list(projections['assumptions'].keys()))

print("\nCreating Excel workbook...")
excel_tool = WorkbookBuilder(output_dir="test_outputs")

try:
    filepath = excel_tool.write_dcf_model(
        deal_name="Test Deal",
        assumptions=projections["assumptions"],
        projections=projections["projections"],
        valuation={
            "wacc": 0.1246,
            "terminal_growth_rate": 0.025,
            "implied_enterprise_value": 100000000000,
            "implied_equity_value": 100000000000,
            "implied_share_price": 100.0,
            "total_borrowings": 0,
            "wacc_breakdown": {"wacc": 0.1246}
        },
        currency="INR",
        historical=projections.get("historical")
    )
    print(f"Excel file created successfully: {filepath}")
except Exception as e:
    import traceback
    print(f"ERROR: {e}")
    traceback.print_exc()
