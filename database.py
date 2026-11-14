# -*- coding: utf-8 -*-
"""
دیتابیس نسخه آنلاین - مدیریت مالی ساختمان
نقش‌ها: مدیر + ساکنین
"""

import sqlite3
import os
from contextlib import contextmanager
from werkzeug.security import generate_password_hash, check_password_hash
import jdatetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "building_finance.db")

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_number TEXT UNIQUE NOT NULL,
                floor INTEGER NOT NULL,
                owner_name TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                status TEXT DEFAULT 'ساکن',
                notes TEXT DEFAULT '',
                password_hash TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                effective_date TEXT NOT NULL,
                monthly_charge INTEGER NOT NULL,
                ownership_charge INTEGER NOT NULL,
                reason TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # status: pending | confirmed | rejected
        c.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                jalali_date TEXT NOT NULL,
                year INTEGER NOT NULL,
                month TEXT NOT NULL,
                unit_number TEXT,
                trans_type TEXT NOT NULL,
                amount INTEGER NOT NULL,
                category TEXT DEFAULT '',
                description TEXT DEFAULT '',
                tracking_code TEXT DEFAULT '',
                status TEXT DEFAULT 'confirmed',
                created_by TEXT DEFAULT 'admin',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                confirmed_at TEXT DEFAULT '',
                confirmed_by TEXT DEFAULT ''
            )
        """)

        # واحدها
        count = c.execute("SELECT COUNT(*) FROM units").fetchone()[0]
        if count == 0:
            units = []
            for floor in range(1, 9):
                for u in range(1, 5):
                    unit_num = f"{floor}0{u}"
                    # رمز پیش‌فرض = شماره واحد
                    pwd = generate_password_hash(unit_num)
                    units.append((unit_num, floor, pwd))
            c.executemany(
                "INSERT INTO units (unit_number, floor, password_hash) VALUES (?, ?, ?)",
                units
            )

        # نرخ اولیه
        if c.execute("SELECT COUNT(*) FROM rates").fetchone()[0] == 0:
            today = jdatetime.date.today().strftime("%Y/%m/%d")
            c.execute(
                "INSERT INTO rates (effective_date, monthly_charge, ownership_charge, reason) VALUES (?,?,?,?)",
                (today, 1500000, 500000, "نرخ اولیه سیستم")
            )

        # تنظیمات + اکانت مدیر
        defaults = {
            "building_name": "مجتمع مسکونی نیکا",
            "initial_current_fund": "50000000",
            "initial_ownership_fund": "120000000",
            "admin_username": "admin",
            "admin_password_hash": generate_password_hash("admin123"),
        }
        for k, v in defaults.items():
            c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

# ---------- تنظیمات ----------
def get_setting(key, default=""):
    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

def set_setting(key, value):
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))

# ---------- احراز هویت ----------
def verify_admin(username, password):
    if username != get_setting("admin_username"):
        return False
    return check_password_hash(get_setting("admin_password_hash"), password)

def verify_resident(unit_number, password):
    with get_db() as conn:
        row = conn.execute(
            "SELECT password_hash FROM units WHERE unit_number=?", (unit_number,)
        ).fetchone()
        if not row or not row["password_hash"]:
            return False
        return check_password_hash(row["password_hash"], password)

def set_unit_password(unit_number, new_password):
    with get_db() as conn:
        conn.execute(
            "UPDATE units SET password_hash=? WHERE unit_number=?",
            (generate_password_hash(new_password), unit_number)
        )

def set_admin_password(new_password):
    set_setting("admin_password_hash", generate_password_hash(new_password))

# ---------- واحدها ----------
def get_all_units():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM units ORDER BY unit_number").fetchall()
        return [dict(r) for r in rows]

def get_unit(unit_number):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM units WHERE unit_number=?", (unit_number,)).fetchone()
        return dict(row) if row else None

def update_unit(unit_number, owner_name, phone, status, notes):
    with get_db() as conn:
        conn.execute(
            """UPDATE units SET owner_name=?, phone=?, status=?, notes=? WHERE unit_number=?""",
            (owner_name, phone, status, notes, unit_number)
        )

# ---------- نرخ‌ها ----------
def get_current_rates():
    with get_db() as conn:
        row = conn.execute("SELECT * FROM rates ORDER BY id DESC LIMIT 1").fetchone()
        if row:
            return dict(row)
        return {"monthly_charge": 1500000, "ownership_charge": 500000, "effective_date": ""}

def add_rate(effective_date, monthly_charge, ownership_charge, reason):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO rates (effective_date, monthly_charge, ownership_charge, reason) VALUES (?,?,?,?)",
            (effective_date, monthly_charge, ownership_charge, reason)
        )

def get_rate_history():
    with get_db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM rates ORDER BY id DESC").fetchall()]

# ---------- تراکنش‌ها ----------
def add_transaction(jalali_date, year, month, unit_number, trans_type, amount,
                    category="", description="", tracking_code="", status="confirmed",
                    created_by="admin"):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO transactions
               (jalali_date, year, month, unit_number, trans_type, amount, category,
                description, tracking_code, status, created_by)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (jalali_date, year, month, unit_number or None, trans_type, amount,
             category, description, tracking_code, status, created_by)
        )

def get_transactions(year=None, month=None, unit_number=None, status=None, limit=300):
    with get_db() as conn:
        q = "SELECT * FROM transactions WHERE 1=1"
        params = []
        if year:
            q += " AND year=?"; params.append(year)
        if month:
            q += " AND month=?"; params.append(month)
        if unit_number:
            q += " AND unit_number=?"; params.append(unit_number)
        if status:
            q += " AND status=?"; params.append(status)
        q += " ORDER BY id DESC LIMIT ?"; params.append(limit)
        return [dict(r) for r in conn.execute(q, params).fetchall()]

def get_pending_payments():
    return get_transactions(status="pending", limit=100)

def confirm_transaction(trans_id, admin_name="admin"):
    with get_db() as conn:
        now = jdatetime.datetime.now().strftime("%Y/%m/%d %H:%M")
        conn.execute(
            """UPDATE transactions SET status='confirmed', confirmed_at=?, confirmed_by=?
               WHERE id=? AND status='pending'""",
            (now, admin_name, trans_id)
        )

def reject_transaction(trans_id, admin_name="admin"):
    with get_db() as conn:
        now = jdatetime.datetime.now().strftime("%Y/%m/%d %H:%M")
        conn.execute(
            """UPDATE transactions SET status='rejected', confirmed_at=?, confirmed_by=?
               WHERE id=? AND status='pending'""",
            (now, admin_name, trans_id)
        )

def delete_transaction(trans_id):
    with get_db() as conn:
        conn.execute("DELETE FROM transactions WHERE id=?", (trans_id,))

# ---------- گزارش و صندوق (فقط تراکنش‌های تأییدشده) ----------
def get_fund_summary():
    rates = get_current_rates()
    with get_db() as conn:
        monthly_income = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE trans_type='پرداخت شارژ ماهانه' AND status='confirmed'"
        ).fetchone()[0]
        ownership_income = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE trans_type='پرداخت شارژ مالکانه' AND status='confirmed'"
        ).fetchone()[0]
        expenses = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE trans_type='هزینه' AND status='confirmed'"
        ).fetchone()[0]

    initial_current = int(get_setting("initial_current_fund", "0"))
    initial_ownership = int(get_setting("initial_ownership_fund", "0"))
    current_fund = initial_current + monthly_income - expenses
    ownership_fund = initial_ownership + ownership_income

    return {
        "initial_current": initial_current,
        "monthly_income": monthly_income,
        "expenses": expenses,
        "current_fund": current_fund,
        "initial_ownership": initial_ownership,
        "ownership_income": ownership_income,
        "ownership_fund": ownership_fund,
        "total_fund": current_fund + ownership_fund,
        "rates": rates
    }

def get_monthly_unit_report(year, month):
    rates = get_current_rates()
    units = get_all_units()
    report = []
    with get_db() as conn:
        for u in units:
            paid_monthly = conn.execute(
                """SELECT COALESCE(SUM(amount),0) FROM transactions
                   WHERE unit_number=? AND trans_type='پرداخت شارژ ماهانه'
                   AND year=? AND month=? AND status='confirmed'""",
                (u["unit_number"], year, month)
            ).fetchone()[0]
            paid_ownership = conn.execute(
                """SELECT COALESCE(SUM(amount),0) FROM transactions
                   WHERE unit_number=? AND trans_type='پرداخت شارژ مالکانه'
                   AND year=? AND month=? AND status='confirmed'""",
                (u["unit_number"], year, month)
            ).fetchone()[0]
            expected_m = rates["monthly_charge"]
            expected_o = rates["ownership_charge"]
            report.append({
                "unit_number": u["unit_number"],
                "owner_name": u["owner_name"],
                "expected_monthly": expected_m,
                "paid_monthly": paid_monthly,
                "debt_monthly": expected_m - paid_monthly,
                "expected_ownership": expected_o,
                "paid_ownership": paid_ownership,
                "debt_ownership": expected_o - paid_ownership,
            })
        expenses = conn.execute(
            """SELECT COALESCE(SUM(amount),0) FROM transactions
               WHERE trans_type='هزینه' AND year=? AND month=? AND status='confirmed'""",
            (year, month)
        ).fetchone()[0]

    return {
        "units": report,
        "expenses": expenses,
        "total_paid_monthly": sum(r["paid_monthly"] for r in report),
        "total_paid_ownership": sum(r["paid_ownership"] for r in report),
        "total_debt_monthly": sum(max(0, r["debt_monthly"]) for r in report),
        "total_debt_ownership": sum(max(0, r["debt_ownership"]) for r in report),
        "year": year,
        "month": month,
        "rates": rates
    }

def get_unit_status(unit_number, year=None, month=None):
    """وضعیت بدهی یک واحد برای ماه جاری یا مشخص‌شده"""
    rates = get_current_rates()
    if year is None or month is None:
        today = jdatetime.date.today()
        year = today.year
        month = ["فروردین","اردیبهشت","خرداد","تیر","مرداد","شهریور",
                 "مهر","آبان","آذر","دی","بهمن","اسفند"][today.month - 1]

    with get_db() as conn:
        paid_m = conn.execute(
            """SELECT COALESCE(SUM(amount),0) FROM transactions
               WHERE unit_number=? AND trans_type='پرداخت شارژ ماهانه'
               AND year=? AND month=? AND status='confirmed'""",
            (unit_number, year, month)
        ).fetchone()[0]
        paid_o = conn.execute(
            """SELECT COALESCE(SUM(amount),0) FROM transactions
               WHERE unit_number=? AND trans_type='پرداخت شارژ مالکانه'
               AND year=? AND month=? AND status='confirmed'""",
            (unit_number, year, month)
        ).fetchone()[0]

    return {
        "year": year,
        "month": month,
        "expected_monthly": rates["monthly_charge"],
        "paid_monthly": paid_m,
        "debt_monthly": rates["monthly_charge"] - paid_m,
        "expected_ownership": rates["ownership_charge"],
        "paid_ownership": paid_o,
        "debt_ownership": rates["ownership_charge"] - paid_o,
    }

# مقداردهی اولیه
init_db()
