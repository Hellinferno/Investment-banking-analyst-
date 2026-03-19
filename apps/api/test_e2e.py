import requests
import json
import os

BASE_URL = "http://127.0.0.1:8000/api/v1"
DEV_BOOTSTRAP_TOKEN = os.getenv("AIBAA_API_TOKEN", "dev-local-token")


def get_auth_headers(role: str = "reviewer") -> dict[str, str]:
    response = requests.post(
        f"{BASE_URL}/auth/dev-token",
        json={"requested_role": role},
        headers={"X-Dev-API-Token": DEV_BOOTSTRAP_TOKEN},
        timeout=30,
    )
    response.raise_for_status()
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


AUTH_HEADERS = get_auth_headers()

with open("C:/tmp/e2e_output.txt", "w", encoding="utf-8") as f:
    r = requests.get(f"{BASE_URL}/health")
    f.write(f"[Health] {r.status_code} → {r.json()}\n")

    deal_data = {
        "name": "Relaxo Footwears DCF",
        "company_name": "Relaxo Footwears Limited",
        "deal_type": "other",
        "industry": "Consumer Staples / Footwear"
    }
    r = requests.post(f"{BASE_URL}/deals", json=deal_data, headers=AUTH_HEADERS)
    deal = r.json().get("data", {})
    deal_id = deal.get("id")
    f.write(f"[Deal] Created: {deal_id}\n")

    agent_payload = {
        "agent_type": "modeling",
        "task_name": "dcf_model",
        "parameters": {
            "projection_years": 7,
            "terminal_growth_rate": 0.025,
        }
    }

    f.write(f"\n[Agent] Running DCF model...\n")
    r = requests.post(
        f"{BASE_URL}/deals/{deal_id}/agents/run",
        json=agent_payload,
        headers=AUTH_HEADERS,
        timeout=120,
    )
    agent_resp = r.json().get("data", {})

    f.write(f"[Agent] Status: {agent_resp.get('status')}\n")

    f.write(f"\n{'='*60}\nAGENT REASONING STEPS\n{'='*60}\n")
    for step in agent_resp.get("steps", []):
        step_type = step.get("type", "?")
        content = step.get("content", "")
        keywords = ["LLM", "extraction", "sanity", "normalize", "revenue", "margin", 
                     "shares", "data source", "WACC", "DCF", "generic", "WARNING"]
        is_important = any(kw.lower() in content.lower() for kw in keywords)
        
        if is_important:
            f.write(f"\n  [{step_type}] {content}\n")
        else:
            f.write(f"  [{step_type}] {content[:150]}...\n")

    vr = agent_resp.get("valuation_result")
    if vr:
        f.write(f"\n{'='*60}\nOUTPUT VALUATION\n{'='*60}\n")
        header = vr.get("header", {})
        assumptions = vr.get("assumptions", {})
        ev_bridge = vr.get("ev_bridge", {})
        eq = vr.get("extraction_quality", {})
        
        f.write(f"  Enterprise Value: {header.get('enterprise_value')}\n")
        f.write(f"  Equity Value:     {header.get('equity_value')}\n")
        f.write(f"  Share Price:      {header.get('implied_share_price')}\n")
        f.write(f"  WACC:             {header.get('wacc')}\n")
        f.write(f"  Shares:           {ev_bridge.get('shares_outstanding')}\n")
        f.write(f"  Net Debt:         {ev_bridge.get('net_debt')}\n")
        f.write(f"\n  Revenue CAGR:     {assumptions.get('revenue_cagr')}\n")
        f.write(f"  EBITDA Margin:    {assumptions.get('avg_ebitda_margin')}\n")
        f.write(f"  CapEx %:          {assumptions.get('cap_ex_percent_rev')}\n")
        f.write(f"  D&A %:            {assumptions.get('da_percent_rev')}\n")
        
        f.write(f"\n  Extraction Mode:  {eq.get('mode')}\n")
        f.write(f"  Data Sources:\n")
        for ds in eq.get("data_sources", []):
            f.write(f"    → {ds}\n")
        
        for w in vr.get("warnings", []):
            f.write(f"\n  WARNING: {w}\n")
    else:
        f.write("\n[ERROR] No valuation_result in response!\n")
        for step in agent_resp.get("steps", []):
            if step.get("type") == "error":
                f.write(f"  Error: {step['content']}\n")

    f.write(f"\n{'='*60}\nTEST COMPLETE\n{'='*60}\n")
    print("Done writing to C:/tmp/e2e_output.txt")
