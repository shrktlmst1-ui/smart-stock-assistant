from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from facility_db import db

router = APIRouter()
bearer = HTTPBearer(auto_error=False)
JWT_SECRET = os.getenv("APP_JWT_SECRET", "facility-mvp-change-this-secret")
JWT_ALG = "HS256"


class SetupRequest(BaseModel):
    facility_name: str = Field(min_length=2, max_length=120)
    admin_email: str = Field(min_length=3, max_length=160)
    admin_password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


class FacilityOut(BaseModel):
    id: int
    name: str
    created_at: str
    model_config = ConfigDict(from_attributes=True)


class BranchIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    address: str = Field(default="", max_length=250)


class BranchOut(BranchIn):
    id: int
    facility_id: int
    created_at: str


class EmployeeIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    employee_no: str = Field(min_length=1, max_length=50)
    phone: str = Field(default="", max_length=40)
    job_title: str = Field(default="", max_length=120)
    branch_id: int | None = None


class EmployeeOut(EmployeeIn):
    id: int
    facility_id: int
    status: str
    created_at: str


def _token(user_id: int, facility_id: int, role: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user_id), "facility_id": facility_id, "role": role, "iat": now, "exp": now + timedelta(hours=24)}, JWT_SECRET, algorithm=JWT_ALG)


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="يلزم تسجيل الدخول")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALG])
        return {"user_id": int(payload["sub"]), "facility_id": int(payload["facility_id"]), "role": payload.get("role", "admin")}
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="جلسة الدخول غير صالحة")


@router.get("/health")
def facility_health():
    with db() as conn:
        conn.execute("SELECT 1").fetchone()
    return {"ok": True, "database": "sqlite"}


@router.post("/auth/setup")
def setup(request: SetupRequest):
    email = request.admin_email.strip().lower()
    with db() as conn:
        if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            raise HTTPException(status_code=409, detail="تم إنشاء مدير النظام مسبقًا")
        cur = conn.execute("INSERT INTO facilities(name) VALUES (?)", (request.facility_name.strip(),))
        facility_id = cur.lastrowid
        password_hash = bcrypt.hashpw(request.admin_password.encode(), bcrypt.gensalt()).decode()
        user_id = conn.execute("INSERT INTO users(facility_id,email,password_hash,role) VALUES (?,?,?,?)", (facility_id, email, password_hash, "admin")).lastrowid
    return {"access_token": _token(user_id, facility_id, "admin"), "token_type": "bearer", "facility_id": facility_id}


@router.post("/auth/login")
def login(request: LoginRequest):
    email = request.email.strip().lower()
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE email = ? ORDER BY id LIMIT 1", (email,)).fetchone()
    if not user or not bcrypt.checkpw(request.password.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="البريد أو كلمة المرور غير صحيحة")
    return {"access_token": _token(user["id"], user["facility_id"], user["role"]), "token_type": "bearer", "facility_id": user["facility_id"]}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    with db() as conn:
        facility = conn.execute("SELECT id,name,created_at FROM facilities WHERE id=?", (user["facility_id"],)).fetchone()
    if not facility:
        raise HTTPException(status_code=404, detail="المنشأة غير موجودة")
    return {"user_id": user["user_id"], "role": user["role"], "facility": dict(facility)}


@router.get("/branches", response_model=list[BranchOut])
def list_branches(user: dict = Depends(current_user)):
    with db() as conn:
        rows = conn.execute("SELECT * FROM branches WHERE facility_id=? ORDER BY id DESC", (user["facility_id"],)).fetchall()
    return [dict(r) for r in rows]


@router.post("/branches", response_model=BranchOut, status_code=201)
def create_branch(request: BranchIn, user: dict = Depends(current_user)):
    with db() as conn:
        cur = conn.execute("INSERT INTO branches(facility_id,name,address) VALUES (?,?,?)", (user["facility_id"], request.name.strip(), request.address.strip()))
        row = conn.execute("SELECT * FROM branches WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.delete("/branches/{branch_id}")
def delete_branch(branch_id: int, user: dict = Depends(current_user)):
    with db() as conn:
        cur = conn.execute("DELETE FROM branches WHERE id=? AND facility_id=?", (branch_id, user["facility_id"]))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="الفرع غير موجود")
    return {"deleted": True}


@router.get("/employees", response_model=list[EmployeeOut])
def list_employees(user: dict = Depends(current_user)):
    with db() as conn:
        rows = conn.execute("SELECT * FROM employees WHERE facility_id=? ORDER BY id DESC", (user["facility_id"],)).fetchall()
    return [dict(r) for r in rows]


@router.post("/employees", response_model=EmployeeOut, status_code=201)
def create_employee(request: EmployeeIn, user: dict = Depends(current_user)):
    with db() as conn:
        if request.branch_id is not None and not conn.execute("SELECT 1 FROM branches WHERE id=? AND facility_id=?", (request.branch_id, user["facility_id"])).fetchone():
            raise HTTPException(status_code=400, detail="الفرع غير تابع للمنشأة")
        try:
            cur = conn.execute("INSERT INTO employees(facility_id,branch_id,name,employee_no,phone,job_title) VALUES (?,?,?,?,?,?)", (user["facility_id"], request.branch_id, request.name.strip(), request.employee_no.strip(), request.phone.strip(), request.job_title.strip()))
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise HTTPException(status_code=409, detail="رقم الموظف مستخدم مسبقًا")
            raise
        row = conn.execute("SELECT * FROM employees WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.delete("/employees/{employee_id}")
def delete_employee(employee_id: int, user: dict = Depends(current_user)):
    with db() as conn:
        cur = conn.execute("DELETE FROM employees WHERE id=? AND facility_id=?", (employee_id, user["facility_id"]))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="الموظف غير موجود")
    return {"deleted": True}
