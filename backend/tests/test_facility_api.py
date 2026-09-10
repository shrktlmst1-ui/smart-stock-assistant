import os
import sqlite3
import subprocess
import sys
import tempfile

DB_PATH = os.path.join(tempfile.gettempdir(), "facility_mvp_test.sqlite3")
os.environ["FACILITY_DB_PATH"] = DB_PATH
try:
    os.remove(DB_PATH)
except FileNotFoundError:
    pass

from fastapi.testclient import TestClient
from main import app


def test_setup_login_and_persistence_across_client_restart():
    with TestClient(app) as client:
        setup = client.post("/api/auth/setup", json={"facility_name": "شركة اختبار", "admin_email": "admin@test.local", "admin_password": "StrongPass123"})
        assert setup.status_code == 200
        token = setup.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        me = client.get("/api/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["facility"]["name"] == "شركة اختبار"

        branch = client.post("/api/branches", headers=headers, json={"name": "الفرع الرئيسي", "address": "الرياض"})
        assert branch.status_code == 201
        branch_id = branch.json()["id"]

        employee = client.post("/api/employees", headers=headers, json={"name": "موظف اختبار", "employee_no": "E-001", "phone": "0500000000", "job_title": "مدير", "branch_id": branch_id})
        assert employee.status_code == 201

        assert client.get("/api/branches", headers=headers).json()[0]["name"] == "الفرع الرئيسي"
        assert client.get("/api/employees", headers=headers).json()[0]["employee_no"] == "E-001"

    # Verify the data is physically committed to the SQLite file, not only held in memory.
    with sqlite3.connect(DB_PATH) as conn:
        assert conn.execute("SELECT name FROM facilities").fetchone()[0] == "شركة اختبار"
        assert conn.execute("SELECT name FROM branches").fetchone()[0] == "الفرع الرئيسي"
        assert conn.execute("SELECT employee_no FROM employees").fetchone()[0] == "E-001"

    # Verify a fresh Python process can reopen the same database and read the saved data.
    check = subprocess.run(
        [sys.executable, "-c", "import os,sqlite3; p=os.environ['FACILITY_DB_PATH']; c=sqlite3.connect(p); assert c.execute('SELECT COUNT(*) FROM facilities').fetchone()[0] == 1; assert c.execute('SELECT COUNT(*) FROM branches').fetchone()[0] == 1; assert c.execute('SELECT COUNT(*) FROM employees').fetchone()[0] == 1"],
        env={**os.environ, "FACILITY_DB_PATH": DB_PATH},
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stderr

    with TestClient(app) as restarted_client:
        login = restarted_client.post("/api/auth/login", json={"email": "admin@test.local", "password": "StrongPass123"})
        assert login.status_code == 200
        restarted_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        branches_after_restart = restarted_client.get("/api/branches", headers=restarted_headers)
        employees_after_restart = restarted_client.get("/api/employees", headers=restarted_headers)
        assert branches_after_restart.status_code == 200
        assert employees_after_restart.status_code == 200
        assert branches_after_restart.json()[0]["name"] == "الفرع الرئيسي"
        assert employees_after_restart.json()[0]["employee_no"] == "E-001"


def test_auth_and_tenant_boundaries():
    with TestClient(app) as client:
        assert client.get("/api/me").status_code == 401
        bad_login = client.post("/api/auth/login", json={"email": "admin@test.local", "password": "wrong-password"})
        assert bad_login.status_code == 401
        assert client.post("/api/auth/setup", json={"facility_name": "شركة ثانية", "admin_email": "second@test.local", "admin_password": "StrongPass123"}).status_code == 409
