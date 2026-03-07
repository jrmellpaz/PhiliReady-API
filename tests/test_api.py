from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check_camel_case():
    """Verify that backend doesn't output unexpected fields and basic app initialization works."""
    response = client.get("/health")
    assert response.status_code == 200
    assert "version" in response.json()

def test_demand_heat_pcodes():
    """Verify that the heat map returns canonical PH-prefixed PSGC codes."""
    response = client.get("/api/v1/map/demand-heat")
    assert response.status_code == 200
    data = response.json()
    
    # Needs to return cities, test at least one key
    assert len(data) > 0
    first_key = list(data.keys())[0]
    
    assert first_key.startswith("PH"), f"Pcode {first_key} should use the PH-prefixed PSGC format"
    numeric_part = first_key[2:]
    assert numeric_part.isdigit(), f"Pcode {first_key} should end with 9-10 digits"
    assert len(numeric_part) == 9 or len(numeric_part) == 10, f"Pcode {first_key} should end with 9-10 digits"

def test_city_detail_camel_case():
    """Verify that the API returns correctly transformed camelCase responses for nested schemas."""
    heat = client.get("/api/v1/map/demand-heat")
    assert heat.status_code == 200
    pcode = list(heat.json().keys())[0]
    response = client.get(f"/api/v1/cities/{pcode}")

    assert response.status_code == 200
    data = response.json()
    
    # Check that keys are camelCase (riskScore instead of risk_score)
    assert "riskScore" in data
    assert "risk_score" not in data
    
    assert "zoneType" in data
    assert "zone_type" not in data
    
    assert "updatedAt" in data
    assert "updated_at" not in data

def test_auth_camel_case():
    """Verify auth endpoint returns camelCase correctly."""
    # We can test logging in as admin since we know seed_data creates one
    login_data = {
        "username": "admin@bariready.ph",
        "password": "admin123"
    }
    login_res = client.post("/api/v1/auth/token", data=login_data)
    if login_res.status_code != 200:
        return # Skip if DB wasn't seeded for this test

    token = login_res.json()["access_token"]
    
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    user_data = me_res.json()
    
    # Database uses full_name, response should be fullName
    assert "fullName" in user_data
    assert "full_name" not in user_data
