from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

print('--- Logging in as Faculty ---')
res = client.post('/api/v1/auth/token', data={'username': 'test_faculty@example.com', 'password': 'password123'})
print(res.status_code, res.json())
fac_token = res.json().get('access_token')

print('\n--- Requesting Vehicle Pass ---')
headers = {'Authorization': f'Bearer {fac_token}'}
payload = {
    'vehicle_number': 'AB12CD3456',
    'vehicle_model': 'Honda Civic',
    'rfid_tag_id': 'RFID-999-888',
    'purpose': 'Commute',
    'valid_until': '2026-12-31T23:59:59Z'
}
res = client.post('/api/v1/passes/vehicle-request', json=payload, headers=headers)
print(res.status_code, res.json())

print('\n--- Logging in as Warden ---')
res = client.post('/api/v1/auth/token', data={'username': 'test_warden@example.com', 'password': 'password123'})
war_token = res.json().get('access_token')

print('\n--- Blacklisting RFID ---')
headers = {'Authorization': f'Bearer {war_token}'}
res = client.post('/api/v1/admin/blacklist-rfid', json={'rfid_tag_id': 'RFID-999-888', 'reason': 'Lost tag'}, headers=headers)
print(res.status_code, res.json())
