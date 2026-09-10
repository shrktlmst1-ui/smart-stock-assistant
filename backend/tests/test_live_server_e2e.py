import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

DB_PATH = os.path.join(tempfile.gettempdir(), "facility_live_server_e2e.sqlite3")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def request(port: int, path: str, method: str = "GET", body: dict | None = None, token: str | None = None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def start_server(port: int):
    env = {**os.environ, "FACILITY_DB_PATH": DB_PATH}
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for _ in range(50):
        try:
            status, _ = request(port, "/health")
            if status == 200:
                return process
        except Exception:
            pass
        time.sleep(0.2)
    output = process.stdout.read() if process.stdout else ""
    process.kill()
    raise AssertionError(f"Backend did not start: {output}
")


def stop_server(process):
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def test_real_backend_restart_persistence():
    try:
        os.remove(DB_PATH)
    except FileNotFoundError:
        pass

    port = free_port()
    server = start_server(port)
    try:
        status, health = request(port, "/health")
        assert status == 200 and health["ok"] is True

        status, setup = request(port, "/api/auth/setup", "POST", {"facility_name": "شركة E2E", "admin_email": "e2e@example.test", "admin_password": "StrongPass123"})
        assert status == 200
        token = setup["access_token"]

        status, me = request(port, "/api/me", token=token)
        assert status == 200 and me["facility"]["name"] == "شركة E2E"

        status, branch = request(port, "/api/branches", "POST", {"name": "فرع E2E", "address": "الرياض"}, token)
        assert status == 201
        branch_id = branch["id"]

        status, employee = request(port, "/api/employees", "POST", {"name": "موظف E2E", "employee_no": "E2E-001", "phone": "0500000000", "job_title": "مدير", "branch_id": branch_id}, token)
        assert status == 201

        stop_server(server)
        server = start_server(port)

        status, login = request(port, "/api/auth/login", "POST", {"email": "e2e@example.test", "password": "StrongPass123"})
        assert status == 200
        token = login["access_token"]

        status, branches = request(port, "/api/branches", token=token)
        assert status == 200 and branches[0]["name"] == "فرع E2E"
        status, employees = request(port, "/api/employees", token=token)
        assert status == 200 and employees[0]["employee_no"] == "E2E-001"
    finally:
        stop_server(server)
