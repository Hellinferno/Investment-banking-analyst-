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

# Test 1: Health check
print("=== Test 1: Health Check ===")
r = requests.get(f"{BASE_URL}/health")
print(f"Status: {r.status_code}")
print(f"Response: {r.json()}")

# Test 2: Create a deal
print("\n=== Test 2: Create Deal ===")
deal_data = {
    "name": "Test Deal",
    "company_name": "Test Co",
    "deal_type": "ma",
    "industry": "Tech"
}
r = requests.post(f"{BASE_URL}/deals", json=deal_data, headers=AUTH_HEADERS)
print(f"Status: {r.status_code}")
response = r.json()
print(f"Response: {json.dumps(response, indent=2)}")

deal_id = response.get('data', {}).get('id')
if deal_id:
    print(f"\nCreated deal ID: {deal_id}")
    
    # Test 3: Run agent
    print("\n=== Test 3: Run Agent ===")
    agent_payload = {
        "agent_type": "modeling",
        "task_name": "dcf_model",
        "parameters": {
            "projection_years": 5,
            "terminal_growth_rate": 0.025
        }
    }
    r = requests.post(f"{BASE_URL}/deals/{deal_id}/agents/run", json=agent_payload, headers=AUTH_HEADERS)
    print(f"Status: {r.status_code}")
    agent_response = r.json()
    print(f"Response status: {agent_response.get('data', {}).get('status')}")
    print(f"Has valuation_result: {'valuation_result' in agent_response.get('data', {})}")

    # Print steps for debugging
    if agent_response.get('data', {}).get('steps'):
        print("\nAgent Steps:")
        for step in agent_response['data']['steps']:
            content = step['content'][:200]
            print(f"  [{step['type']}] {content}...")

        # Check for error step
        error_step = next((s for s in agent_response['data']['steps'] if s['type'] == 'error'), None)
        if error_step:
            print(f"\n[ERROR DETAILS] {error_step['content']}")

    if agent_response.get('data', {}).get('valuation_result'):
        print("[SUCCESS] Valuation result received successfully!")
        vr = agent_response['data']['valuation_result']
        print(f"  - Enterprise Value: {vr.get('header', {}).get('enterprise_value')}")
        print(f"  - Equity Value: {vr.get('header', {}).get('equity_value')}")
        print(f"  - Share Price: {vr.get('header', {}).get('implied_share_price')}")
    else:
        print("[WARNING] No valuation_result in response")
else:
    print("Failed to create deal")

print("\n=== All Tests Complete ===")
