import urllib.request
import json
import requests

# Create Deal First
deal_url = 'http://localhost:8000/api/v1/deals'
deal_data = json.dumps({'name':'Project Titan', 'company_name':'Massive Dynamic', 'deal_type':'ma_buyside', 'industry':'Technology'}).encode('utf-8')
req = urllib.request.Request(deal_url, data=deal_data, headers={'Content-Type': 'application/json'})

with urllib.request.urlopen(req) as resp:
    deal_resp = json.loads(resp.read().decode('utf-8'))
    deal_id = deal_resp['data']['id']
    print(f'Successfully created deal: {deal_id}')

# Mock Upload File
upload_url = f'http://localhost:8000/api/v1/deals/{deal_id}/documents'

# Write a dummy test file
with open('test_upload.csv', 'w') as f:
    f.write('Revenue,Cost\n100,50\n200,80')

# Upload dummy test file via multipart form
with open('test_upload.csv', 'rb') as f:
    files = {'files': ('test_upload.csv', f, 'text/csv')}
    resp = requests.post(upload_url, files=files, data={'category': 'financial'})
    
    upload_data = resp.json()
    print(f'Upload response status: {resp.status_code}')
    print(f'Parsed new document ID: {upload_data["data"]["uploaded"][0]["id"]}')
