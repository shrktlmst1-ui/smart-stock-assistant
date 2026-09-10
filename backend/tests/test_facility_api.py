import os
import tempfile

os.environ["FACILITY_DB_PATH"] = os.path.join(tempfile.gettempdir(), "facility_mvp_test.sqlite3")
try:
    os.remove(os.environ["FACILITY_DB_PATH"])
except FileNotFoundError:
    pass

from fastapi.testclient import TestClient
from main import app


def test_setup_login_and_persistence():
    with TestClient(app) as client:
        setup = client.post("/api/auth/setup", json={"facility_name": "شركة اختبار", "admin_email": "admin@test.local", "admin_password": "StrongPass123"})
        assert setup.status_code == 200
        token = setup.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        branch = client.post("/api/branches", headers=headers, json={"name": "الفرع الرئيسي", "address": "الرياض"})
        assert branch.status_code == 201
        branch_id = branch.json()["id"]

        employee = client.post("/api/employees", headers=headers, json={"name": "موظف اختبار", "employee_no": "E-001", "phone": "0500000000", "job_title": "مدير", "branch_id": branch_id})
        assert employee.status_code == 201

        employees = client.get("/api/employees", headers=headers)
        assert employees.status_code == 200
        assert employees.json()[0]["employee_no"] == "E-001"

        login = client.post("/api/auth/login", json={"email": "admin@test.local", "password": "StrongPass123"})
        assert login.status_code == 200

        branches_after_login = client.get("/api/branches", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
        assert branches_after_login.status_code == 200
        assert branches_after_login.json()[0]["name"] == "الفرع الرئيسي"
