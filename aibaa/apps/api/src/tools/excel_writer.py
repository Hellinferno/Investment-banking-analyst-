import os
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from typing import Dict, Any, List
from openpyxl.utils import get_column_letter

class WorkbookBuilder:
    """Tool to generate formatting-compliant IB Excel Models."""
    
    def __init__(self, output_dir: str = "aibaa/data/outputs"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        
        # IB Standard Formatting
        self.header_font = Font(name='Arial', bold=True, color='FFFFFF')
        self.header_fill = PatternFill(start_color='000000', end_color='000000', fill_type='solid')
        self.calc_font = Font(name='Arial', color='0000FF') # Blue for calculated
        self.hardcode_font = Font(name='Arial', color='000000') # Black for hardcoded
        self.hist_font = Font(name='Arial', color='008000')  # Green for historical actuals
        self.align_center = Alignment(horizontal='center')
        self.pct_font = Font(name='Arial', color='808080', italic=True)  # Grey for % rows
        
        thin_border = Side(border_style="thin", color="000000")
        self.border_bottom = Border(bottom=thin_border)
        self.border_top = Border(top=thin_border)
        
    def _apply_header_style(self, cell):
        cell.font = self.header_font
        cell.fill = self.header_fill
        cell.alignment = self.align_center
        
    def write_dcf_model(self, deal_name: str, assumptions: Dict[str, float], 
                        projections: Dict[str, List[float]], valuation: Dict[str, Any], 
                        currency: str = "INR", historical: Dict[str, Any] = None) -> str:
        """Generates a multi-tab DCF Workbook and saves it to disk."""
        wb = openpyxl.Workbook()
        is_private_company = bool(valuation.get("is_private_company"))
        valuation_basis = valuation.get("valuation_basis", "share_price")
        liquidity_discount = float(valuation.get("liquidity_discount", 0) or 0)
        control_premium = float(valuation.get("control_premium", 0) or 0)
        
        # Dynamic currency format
        currency_symbol = "₹" if currency == "INR" else "$"
        curr_fmt = f'{currency_symbol}#,##0.00'
        
        # FY labels from projections (e.g. FY2026E, FY2027E...)
        fy_labels = projections.get("fy_labels", [f"Year {i+1}" for i in range(5)])
        hist_labels = historical.get("fy_labels", []) if historical else []
        num_hist = len(hist_labels)
        num_proj = len(fy_labels)
        
        # --- Tab 1: Assumptions ---
        ws_assumptions = wb.active
        ws_assumptions.title = "Assumptions"
        ws_assumptions["A1"] = f"{deal_name} - Key Assumptions"
        ws_assumptions["A1"].font = Font(name='Arial', size=14, bold=True)
        
        r = 3
        for k, v in assumptions.items():
            if k == "base_fy":
                continue  # Don't show internal parameter
            if isinstance(v, dict):
                continue  # Skip nested dicts like working_capital_days
            ws_assumptions.cell(row=r, column=1, value=k.replace("_", " ").title())
            c = ws_assumptions.cell(row=r, column=2, value=v)
            c.font = self.hardcode_font
            c.number_format = '0.00%' if isinstance(v, (int, float)) and v < 1 else '#,##0.00'
            r += 1
            
        r += 1
        ws_assumptions.cell(row=r, column=1, value="WACC")
        ws_assumptions.cell(row=r, column=2, value=valuation["wacc"]).number_format = '0.00%'
        r += 1
        ws_assumptions.cell(row=r, column=1, value="Terminal Growth Rate")
        ws_assumptions.cell(row=r, column=2, value=valuation["terminal_growth_rate"]).number_format = '0.00%'
        
        # --- WACC Breakdown Sub-Section ---
        wacc_bk = valuation.get("wacc_breakdown", {})
        if wacc_bk:
            r += 2
            ws_assumptions.cell(row=r, column=1, value="WACC Calculation Breakdown").font = Font(name='Arial', bold=True, italic=True)
            if "note" in wacc_bk:
                r += 1
                ws_assumptions.cell(row=r, column=1, value=wacc_bk["note"]).font = Font(name='Arial', color='808080')
            else:
                if wacc_bk.get("method") == "build_up":
                    wacc_fields = [
                        ("Risk-Free Rate", "risk_free_rate", True),
                        ("Equity Risk Premium", "equity_risk_premium", True),
                        ("Size Premium", "size_premium", True),
                        ("Specific Risk Premium", "specific_risk_premium", True),
                        ("Cost of Equity (Build-Up)", "cost_of_equity", True),
                        ("Cost of Debt", "cost_of_debt", True),
                        ("After-Tax Cost of Debt", "after_tax_cost_of_debt", True),
                        ("Weight of Equity", "weight_of_equity", True),
                        ("Weight of Debt", "weight_of_debt", True)
                    ]
                else:
                    wacc_fields = [
                        ("Risk-Free Rate (10Y G-Sec)", "risk_free_rate", True),
                        ("Equity Risk Premium", "equity_risk_premium", True),
                        ("Beta", "beta", False),
                        ("Cost of Equity (CAPM)", "cost_of_equity", True),
                        ("Cost of Debt", "cost_of_debt", True),
                        ("After-Tax Cost of Debt", "after_tax_cost_of_debt", True),
                        ("Weight of Equity", "weight_of_equity", True),
                        ("Weight of Debt", "weight_of_debt", True)
                    ]
                for label, dict_key, is_pct in wacc_fields:
                    if dict_key in wacc_bk:
                        r += 1
                        ws_assumptions.cell(row=r, column=1, value=label)
                        c = ws_assumptions.cell(row=r, column=2, value=wacc_bk[dict_key])
                        c.font = self.calc_font
                        c.number_format = '0.00%' if is_pct else '0.00'
                        
        ws_assumptions.column_dimensions['A'].width = 40
        
        # --- Tab 2: Projections ---
        ws_proj = wb.create_sheet(title="Projections")
        ws_proj["A1"] = f"{deal_name} - Financial Projections ({currency})"
        ws_proj["A1"].font = Font(name='Arial', size=14, bold=True)
        
        # Build headers: Metric | FY2023A | FY2024A | FY2025A | FY2026E | FY2027E | ...
        all_headers = ["Metric"] + hist_labels + fy_labels
        for col, header in enumerate(all_headers, start=1):
            cell = ws_proj.cell(row=3, column=col, value=header)
            self._apply_header_style(cell)
        
        # Data start column: after Metric column
        hist_col_start = 2  # Column B
        proj_col_start = hist_col_start + num_hist  # After historical columns
        
        # Revenue row with historical + projected
        current_row = 4
        
        # Helper to write a metric row (historical + projected)
        def write_metric_row(row, label, hist_vals, proj_vals, is_pct=False, is_ufcf=False):
            cell_label = ws_proj.cell(row=row, column=1, value=label)
            cell_label.font = Font(name='Arial', bold=True)
            if is_ufcf:
                cell_label.border = self.border_top
            
            # Historical values (green font)
            if hist_vals:
                for i, val in enumerate(hist_vals):
                    cell = ws_proj.cell(row=row, column=hist_col_start + i, value=val)
                    cell.font = self.hist_font
                    cell.number_format = '0.00%' if is_pct else '#,##0.00'
            
            # Projected values (blue font)
            for i, val in enumerate(proj_vals):
                cell = ws_proj.cell(row=row, column=proj_col_start + i, value=val)
                cell.font = self.pct_font if is_pct else self.calc_font
                cell.number_format = '0.00%' if is_pct else '#,##0.00'
                if is_ufcf:
                    cell.border = self.border_top
        
        # Historical EBITDA values
        hist_revenue = historical.get("revenue", []) if historical else []
        hist_ebitda = historical.get("ebitda", []) if historical else []
        hist_margins = historical.get("ebitda_margins", []) if historical else []
        
        # Compute historical revenue growth
        hist_growth = []
        for i in range(len(hist_revenue)):
            if i == 0:
                hist_growth.append(None)  # No prior year
            else:
                g = (hist_revenue[i] / hist_revenue[i-1] - 1) * 100 if hist_revenue[i-1] > 0 else 0
                hist_growth.append(round(g, 2))
        
        # Convert historical margins to percentages for display
        hist_margins_pct = [round(m * 100, 2) for m in hist_margins]
        
        # Write all metric rows
        write_metric_row(current_row, "Revenue", hist_revenue, projections.get("revenue", []))
        current_row += 1
        write_metric_row(current_row, "  Revenue Growth %", hist_growth, projections.get("revenue_growth_pct", []), is_pct=False)
        current_row += 1
        write_metric_row(current_row, "EBITDA", hist_ebitda, projections.get("ebitda", []))
        current_row += 1
        write_metric_row(current_row, "  EBITDA Margin %", hist_margins_pct, projections.get("ebitda_margin_pct", []), is_pct=False)
        current_row += 1
        write_metric_row(current_row, "Less: D&A", [], projections.get("da", []))
        current_row += 1
        write_metric_row(current_row, "EBIT", [], projections.get("ebit", []))
        current_row += 1
        write_metric_row(current_row, "Less: Taxes", [], projections.get("taxes", []))
        current_row += 1
        write_metric_row(current_row, "EBIAT", [], projections.get("ebiat", []))
        current_row += 1
        write_metric_row(current_row, "Plus: D&A", [], projections.get("da", []))
        current_row += 1
        write_metric_row(current_row, "Less: CapEx", [], projections.get("capex", []))
        current_row += 1
        write_metric_row(current_row, "Less: Change in NWC", [], projections.get("nwc_change", []))
        current_row += 1
        write_metric_row(current_row, "Unlevered Free Cash Flow", [], projections.get("ufcf", []), is_ufcf=True)
        
        ws_proj.column_dimensions['A'].width = 30
        for col_idx in range(2, 2 + num_hist + num_proj):
            ws_proj.column_dimensions[get_column_letter(col_idx)].width = 18
            
        # --- Tab 3: Valuation ---
        ws_val = wb.create_sheet(title="Valuation")
        ws_val["A1"] = f"{deal_name} - DCF Valuation ({currency})"
        ws_val["A1"].font = Font(name='Arial', size=14, bold=True)
        
        # Use FY labels for projected columns only
        val_headers = ["Metric"] + fy_labels
        for col, header in enumerate(val_headers, start=1):
            cell = ws_val.cell(row=3, column=col, value=header)
            self._apply_header_style(cell)
            
        current_row = 4
        metrics_val = [
            ("Unlevered Free Cash Flow", projections.get("ufcf", [])),
            ("Discount Factor", valuation.get("discount_factors", [])),
            ("PV of Free Cash Flow", valuation.get("pv_of_fcf_array", []))
        ]
        
        for metric_name, values in metrics_val:
            ws_val.cell(row=current_row, column=1, value=metric_name).font = Font(name='Arial', bold=True)
            for col, val in enumerate(values, start=2):
                cell = ws_val.cell(row=current_row, column=col, value=val)
                cell.font = self.calc_font
                cell.number_format = '0.0000' if "Discount" in metric_name else '#,##0.00'
            current_row += 1
            
        current_row += 2
        
        # Equity Bridge with separate Borrowings and Cash
        net_debt_val = valuation.get("net_debt", 0)
        total_borrowings = valuation.get("total_borrowings", abs(net_debt_val) * 1.2 if net_debt_val > 0 else 0)
        cash_and_equiv = total_borrowings - net_debt_val if net_debt_val > 0 else abs(net_debt_val) + total_borrowings
        
        equity_bridge = [
            ("Sum of PV of FCFs", valuation.get("pv_of_fcf_sum", 0)),
            ("PV of Terminal Value", valuation.get("pv_of_tv", 0)),
            ("Implied Enterprise Value", valuation.get("implied_enterprise_value", 0)),
            ("Less: Total Borrowings", total_borrowings),
            ("Add: Cash & Equivalents", cash_and_equiv),
            (f"Net Debt" if net_debt_val >= 0 else "Net Cash", abs(net_debt_val)),
        ]
        if is_private_company or valuation_basis == "equity_value":
            equity_bridge.extend([
                ("Pre-Adjustment Equity Value", valuation.get("pre_private_adjustment_equity_value", valuation.get("implied_equity_value", 0))),
                ("Liquidity Discount %", liquidity_discount),
                ("Control Premium %", control_premium),
                ("Implied Equity Value", valuation.get("implied_equity_value", 0)),
            ])
        else:
            equity_bridge.extend([
                ("Implied Equity Value", valuation.get("implied_equity_value", 0)),
                ("Shares Outstanding", valuation.get("shares_outstanding", 1)),
                ("Implied Share Price", valuation.get("implied_share_price", 0)),
            ])
        
        for name, val in equity_bridge:
            c_name = ws_val.cell(row=current_row, column=1, value=name)
            c_name.font = Font(name='Arial', bold=True)
            if "Enterprise" in name or "Equity Value" in name or "Share Price" in name:
                c_name.border = self.border_bottom
            c_val = ws_val.cell(row=current_row, column=2, value=val)
            c_val.font = self.calc_font
            if "Discount %" in name or "Premium %" in name:
                c_val.number_format = '0.00%'
            elif "Shares" in name:
                c_val.number_format = '#,##0'
            else:
                c_val.number_format = curr_fmt if "Price" in name or "Value" in name or "Sum" in name or "Borrowings" in name or "Cash" in name or "Net" in name or "Terminal" in name else '#,##0'
            if "Enterprise" in name or "Equity Value" in name or "Share Price" in name:
                c_val.border = self.border_bottom
            current_row += 1
            
        ws_val.column_dimensions['A'].width = 30
        for col_idx in range(2, 2 + num_proj):
            ws_val.column_dimensions[get_column_letter(col_idx)].width = 18

        # --- Tab 4: Sensitivity Analysis ---
        ws_sens = wb.create_sheet(title="Sensitivity Analysis")
        metric_title = "Implied Equity Value" if is_private_company or valuation_basis == "equity_value" else "Implied Share Price"
        ws_sens["A1"] = f"{deal_name} - {metric_title} Sensitivity ({currency})"
        ws_sens["A1"].font = Font(name='Arial', size=14, bold=True)
        
        ws_sens["A3"] = "Sensitivity: WACC vs. Terminal Growth Rate"
        ws_sens["A3"].font = Font(name="Arial", bold=True)
        
        metric_row = current_row - 1
        ws_sens["B4"] = f"='Valuation'!B{metric_row}"
        ws_sens["B4"].font = self.calc_font
        ws_sens["B4"].number_format = curr_fmt
        
        tgr_variations = [-0.01, -0.005, 0, 0.005, 0.01]
        wacc_variations = [-0.02, -0.01, 0, 0.01, 0.02]
        
        base_tgr = valuation["terminal_growth_rate"]
        base_wacc = valuation["wacc"]
        
        # Headers TGR
        for i, var in enumerate(tgr_variations):
            c = ws_sens.cell(row=4, column=3+i, value=base_tgr + var)
            c.number_format = "0.0%"
            c.font = Font(bold=True)
            
        # Headers WACC
        for i, var in enumerate(wacc_variations):
            c = ws_sens.cell(row=5+i, column=2, value=base_wacc + var)
            c.number_format = "0.0%"
            c.font = Font(bold=True)
            
        # Static sensitivity point calculation
        for r_idx, w_var in enumerate(wacc_variations):
            for c_idx, t_var in enumerate(tgr_variations):
                w_test = base_wacc + w_var
                t_test = base_tgr + t_var
                
                fcf_pv_sum = 0
                projs = projections.get("ufcf", [])
                for i, cf in enumerate(projs):
                    fcf_pv_sum += cf / ((1 + w_test) ** (i + 1))
                    
                tv = (projs[-1] * (1 + t_test)) / (w_test - t_test)
                tv_pv = tv / ((1 + w_test) ** len(projs))
                ev = fcf_pv_sum + tv_pv
                eq = ev - valuation.get("net_debt", 0)
                if is_private_company or valuation_basis == "equity_value":
                    metric_value = eq * (1 - liquidity_discount) * (1 + control_premium)
                else:
                    metric_value = eq / valuation.get("shares_outstanding", 1) if valuation.get("shares_outstanding", 1) > 0 else 0
                
                c = ws_sens.cell(row=5+r_idx, column=3+c_idx, value=metric_value)
                c.number_format = curr_fmt
                c.font = self.calc_font

        ws_sens.column_dimensions['A'].width = 10
        ws_sens.column_dimensions['B'].width = 15
        for col in ['C', 'D', 'E', 'F', 'G']:
            ws_sens.column_dimensions[col].width = 15
            
        # Save File
        safe_name = deal_name.replace(" ", "_").lower()
        filename = f"dcf_model_{safe_name}.xlsx"
        filepath = os.path.join(self.output_dir, filename)
        
        wb.save(filepath)
        return filepath
