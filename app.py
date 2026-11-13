# -*- coding: utf-8 -*-
"""
سیستم مدیریت مالی ساختمان - نسخه آنلاین چندکاربره
مدیر + ساکنین (اعلام واریزی + تأیید توسط مدیر)
"""

import os
from functools import wraps
from io import BytesIO

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, send_file
)
import jdatetime

from database import (
    get_setting, set_setting, get_current_rates, get_all_units, get_unit,
    update_unit, add_transaction, get_transactions, get_fund_summary,
    get_monthly_unit_report, add_rate, get_rate_history, delete_transaction,
    verify_admin, verify_resident, set_unit_password, set_admin_password,
    get_pending_payments, confirm_transaction, reject_transaction,
    get_unit_status, DB_PATH
)

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import arabic_reshaper
from bidi.algorithm import get_display

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "building-finance-change-this-secret-key-in-production-2025")
app.config["TEMPLATES_AUTO_RELOAD"] = True

FONT_PATH = os.path.join(os.path.dirname(__file__), "static", "fonts", "Vazirmatn-Regular.ttf")
if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont("Vazir", FONT_PATH))
    PDF_FONT = "Vazir"
else:
    PDF_FONT = "Helvetica"

PERSIAN_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
]

def fa(text):
    if not text:
        return ""
    return get_display(arabic_reshaper.reshape(str(text)))

def format_money(amount):
    try:
        return f"{int(amount):,}"
    except Exception:
        return str(amount)

@app.context_processor
def inject_globals():
    return {
        "building_name": get_setting("building_name", "مجتمع مسکونی"),
        "today_jalali": jdatetime.date.today().strftime("%Y/%m/%d"),
        "persian_months": PERSIAN_MONTHS,
        "format_money": format_money,
        "user": {
            "role": session.get("role"),
            "username": session.get("username"),
            "unit_number": session.get("unit_number"),
        }
    }

# ---------- دکوراتورهای دسترسی ----------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("role"):
            flash("لطفاً وارد شوید.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role") != "admin":
            flash("دسترسی فقط برای مدیر ساختمان است.", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def resident_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role") != "resident":
            flash("دسترسی فقط برای ساکنین است.", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ============================================================
# ورود / خروج
# ============================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("role"):
        if session["role"] == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("resident_dashboard"))

    if request.method == "POST":
        role = request.form.get("role")
        if role == "admin":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            if verify_admin(username, password):
                session.clear()
                session["role"] = "admin"
                session["username"] = username
                flash("ورود مدیر موفقیت‌آمیز بود.", "success")
                return redirect(url_for("admin_dashboard"))
            flash("نام کاربری یا رمز عبور مدیر اشتباه است.", "danger")
        else:
            unit_number = request.form.get("unit_number", "").strip()
            password = request.form.get("password", "")
            if verify_resident(unit_number, password):
                session.clear()
                session["role"] = "resident"
                session["unit_number"] = unit_number
                session["username"] = unit_number
                flash(f"ورود واحد {unit_number} موفقیت‌آمیز بود.", "success")
                return redirect(url_for("resident_dashboard"))
            flash("شماره واحد یا رمز عبور اشتباه است.", "danger")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("با موفقیت خارج شدید.", "info")
    return redirect(url_for("login"))

# ============================================================
# پنل مدیر
# ============================================================
@app.route("/")
def index():
    if session.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))
    if session.get("role") == "resident":
        return redirect(url_for("resident_dashboard"))
    return redirect(url_for("login"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    funds = get_fund_summary()
    recent = get_transactions(limit=8)
    pending = get_pending_payments()
    rates = get_current_rates()
    return render_template(
        "admin/dashboard.html",
        funds=funds, recent=recent, pending=pending, rates=rates
    )

@app.route("/admin/units")
@admin_required
def admin_units():
    units = get_all_units()
    return render_template("admin/units.html", units=units)

@app.route("/admin/units/update", methods=["POST"])
@admin_required
def admin_units_update():
    unit_number = request.form.get("unit_number")
    update_unit(
        unit_number,
        request.form.get("owner_name", ""),
        request.form.get("phone", ""),
        request.form.get("status", "ساکن"),
        request.form.get("notes", "")
    )
    # تغییر رمز اگر وارد شده باشد
    new_pass = request.form.get("new_password", "").strip()
    if new_pass:
        set_unit_password(unit_number, new_pass)
        flash(f"اطلاعات و رمز واحد {unit_number} به‌روز شد.", "success")
    else:
        flash(f"اطلاعات واحد {unit_number} ذخیره شد.", "success")
    return redirect(url_for("admin_units"))

@app.route("/admin/transactions")
@admin_required
def admin_transactions():
    year = request.args.get("year", type=int)
    month = request.args.get("month")
    status = request.args.get("status")
    trans = get_transactions(year=year, month=month, status=status, limit=300)
    units = get_all_units()
    rates = get_current_rates()
    return render_template(
        "admin/transactions.html",
        transactions=trans, units=units, rates=rates,
        selected_year=year, selected_month=month, selected_status=status
    )

@app.route("/admin/transactions/add", methods=["POST"])
@admin_required
def admin_transactions_add():
    try:
        amount = int(request.form.get("amount", "0").replace(",", ""))
        if amount <= 0:
            flash("مبلغ باید بزرگ‌تر از صفر باشد.", "danger")
            return redirect(url_for("admin_transactions"))
        add_transaction(
            jalali_date=request.form.get("jalali_date", "").strip(),
            year=int(request.form.get("year")),
            month=request.form.get("month"),
            unit_number=request.form.get("unit_number") or None,
            trans_type=request.form.get("trans_type"),
            amount=amount,
            category=request.form.get("category", ""),
            description=request.form.get("description", ""),
            tracking_code=request.form.get("tracking_code", ""),
            status="confirmed",
            created_by=session.get("username", "admin")
        )
        flash("تراکنش با موفقیت ثبت شد.", "success")
    except Exception as e:
        flash(f"خطا: {e}", "danger")
    return redirect(url_for("admin_transactions"))

@app.route("/admin/transactions/delete/<int:trans_id>", methods=["POST"])
@admin_required
def admin_transactions_delete(trans_id):
    delete_transaction(trans_id)
    flash("تراکنش حذف شد.", "warning")
    return redirect(url_for("admin_transactions"))

@app.route("/admin/pending")
@admin_required
def admin_pending():
    pending = get_pending_payments()
    return render_template("admin/pending.html", pending=pending)

@app.route("/admin/pending/confirm/<int:trans_id>", methods=["POST"])
@admin_required
def admin_pending_confirm(trans_id):
    confirm_transaction(trans_id, session.get("username", "admin"))
    flash("واریزی تأیید شد و به صندوق اضافه گردید.", "success")
    return redirect(url_for("admin_pending"))

@app.route("/admin/pending/reject/<int:trans_id>", methods=["POST"])
@admin_required
def admin_pending_reject(trans_id):
    reject_transaction(trans_id, session.get("username", "admin"))
    flash("واریزی رد شد.", "warning")
    return redirect(url_for("admin_pending"))

@app.route("/admin/report")
@admin_required
def admin_report():
    today = jdatetime.date.today()
    year = request.args.get("year", type=int) or today.year
    month = request.args.get("month") or PERSIAN_MONTHS[today.month - 1]
    report = get_monthly_unit_report(year, month)
    return render_template("admin/report.html", report=report, year=year, month=month)

@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "rates":
            add_rate(
                request.form.get("effective_date"),
                int(request.form.get("monthly_charge", "0").replace(",", "")),
                int(request.form.get("ownership_charge", "0").replace(",", "")),
                request.form.get("reason", "")
            )
            flash("نرخ جدید ثبت شد.", "success")
        elif action == "general":
            set_setting("building_name", request.form.get("building_name", ""))
            set_setting("initial_current_fund", request.form.get("initial_current_fund", "0").replace(",", ""))
            set_setting("initial_ownership_fund", request.form.get("initial_ownership_fund", "0").replace(",", ""))
            flash("تنظیمات ذخیره شد.", "success")
        elif action == "admin_password":
            p1 = request.form.get("new_password", "")
            p2 = request.form.get("new_password2", "")
            if p1 and p1 == p2 and len(p1) >= 4:
                set_admin_password(p1)
                flash("رمز مدیر تغییر کرد.", "success")
            else:
                flash("رمز جدید معتبر نیست یا تکرار آن مطابقت ندارد.", "danger")
        return redirect(url_for("admin_settings"))

    return render_template(
        "admin/settings.html",
        rates=get_current_rates(),
        history=get_rate_history(),
        building_name=get_setting("building_name"),
        initial_current=get_setting("initial_current_fund"),
        initial_ownership=get_setting("initial_ownership_fund"),
    )

# ============================================================
# پنل ساکن
# ============================================================
@app.route("/resident")
@resident_required
def resident_dashboard():
    unit_number = session["unit_number"]
    unit = get_unit(unit_number)
    status = get_unit_status(unit_number)
    my_trans = get_transactions(unit_number=unit_number, limit=20)
    pending = [t for t in my_trans if t["status"] == "pending"]
    return render_template(
        "resident/dashboard.html",
        unit=unit, status=status, transactions=my_trans, pending=pending
    )

@app.route("/resident/payment", methods=["GET", "POST"])
@resident_required
def resident_payment():
    unit_number = session["unit_number"]
    rates = get_current_rates()
    today = jdatetime.date.today()

    if request.method == "POST":
        try:
            amount = int(request.form.get("amount", "0").replace(",", ""))
            if amount <= 0:
                flash("مبلغ معتبر وارد کنید.", "danger")
                return redirect(url_for("resident_payment"))
            trans_type = request.form.get("trans_type")
            if trans_type not in ("پرداخت شارژ ماهانه", "پرداخت شارژ مالکانه"):
                flash("نوع پرداخت نامعتبر است.", "danger")
                return redirect(url_for("resident_payment"))

            add_transaction(
                jalali_date=request.form.get("jalali_date", "").strip(),
                year=int(request.form.get("year")),
                month=request.form.get("month"),
                unit_number=unit_number,
                trans_type=trans_type,
                amount=amount,
                description=request.form.get("description", ""),
                tracking_code=request.form.get("tracking_code", "").strip(),
                status="pending",
                created_by=unit_number
            )
            flash("اعلام واریزی شما ثبت شد و پس از تأیید مدیر به حساب منظور می‌شود.", "success")
            return redirect(url_for("resident_dashboard"))
        except Exception as e:
            flash(f"خطا در ثبت: {e}", "danger")

    return render_template(
        "resident/payment.html",
        rates=rates,
        year=today.year,
        month=PERSIAN_MONTHS[today.month - 1]
    )

@app.route("/resident/history")
@resident_required
def resident_history():
    unit_number = session["unit_number"]
    trans = get_transactions(unit_number=unit_number, limit=100)
    return render_template("resident/history.html", transactions=trans)

# ============================================================
# PDF گزارش (فقط مدیر)
# ============================================================
@app.route("/admin/report/pdf")
@admin_required
def admin_report_pdf():
    today = jdatetime.date.today()
    year = request.args.get("year", type=int) or today.year
    month = request.args.get("month") or PERSIAN_MONTHS[today.month - 1]
    report = get_monthly_unit_report(year, month)
    building = get_setting("building_name", "مجتمع مسکونی")

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=15*mm, leftMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)

    title_style = ParagraphStyle("T", fontName=PDF_FONT, fontSize=14, alignment=1,
                                 textColor=colors.HexColor("#1F4E79"), spaceAfter=6)
    normal_style = ParagraphStyle("N", fontName=PDF_FONT, fontSize=9, alignment=2, leading=13)

    elements = []
    elements.append(Paragraph(fa(f"گزارش مالی ماهانه - {building}"), title_style))
    elements.append(Paragraph(fa(f"ماه: {month} {year} | تاریخ تهیه: {jdatetime.date.today().strftime('%Y/%m/%d')}"), normal_style))
    elements.append(Spacer(1, 6))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1F4E79")))
    elements.append(Spacer(1, 8))

    summary = [
        [fa("جمع پرداخت شارژ ماهانه"), fa(format_money(report["total_paid_monthly"]) + " ریال")],
        [fa("جمع پرداخت شارژ مالکانه"), fa(format_money(report["total_paid_ownership"]) + " ریال")],
        [fa("جمع بدهی ماهانه"), fa(format_money(report["total_debt_monthly"]) + " ریال")],
        [fa("جمع هزینه‌ها"), fa(format_money(report["expenses"]) + " ریال")],
    ]
    st = Table(summary, colWidths=[90*mm, 70*mm])
    st.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), PDF_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F5F5F5")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    elements.append(st)
    elements.append(Spacer(1, 10))

    header = [fa("بدهی مالکانه"), fa("پرداخت مالکانه"), fa("بدهی ماهانه"),
              fa("پرداخت ماهانه"), fa("واحد")]
    data = [header]
    for u in report["units"]:
        data.append([
            fa(format_money(u["debt_ownership"])),
            fa(format_money(u["paid_ownership"])),
            fa(format_money(u["debt_monthly"])),
            fa(format_money(u["paid_monthly"])),
            fa(u["unit_number"]),
        ])
    data.append([
        fa(format_money(report["total_debt_ownership"])),
        fa(format_money(report["total_paid_ownership"])),
        fa(format_money(report["total_debt_monthly"])),
        fa(format_money(report["total_paid_monthly"])),
        fa("جمع"),
    ])

    table = Table(data, colWidths=[32*mm, 32*mm, 32*mm, 32*mm, 25*mm], repeatRows=1)
    style_cmds = [
        ("FONTNAME", (0, 0), (-1, -1), PDF_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#D6EAF8")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]
    for i, u in enumerate(report["units"], 1):
        if u["debt_monthly"] > 0:
            style_cmds.append(("BACKGROUND", (2, i), (2, i), colors.HexColor("#FFCDD2")))
        if u["debt_ownership"] > 0:
            style_cmds.append(("BACKGROUND", (0, i), (0, i), colors.HexColor("#FFCDD2")))
    table.setStyle(TableStyle(style_cmds))
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True,
                     download_name=f"report_{year}_{month}.pdf",
                     mimetype="application/pdf")

# ============================================================
if __name__ == "__main__":
    print("=" * 55)
    print("  سیستم مدیریت مالی ساختمان (نسخه آنلاین)")
    print("  آدرس: http://127.0.0.1:5000")
    print("  مدیر: admin / admin123")
    print("  ساکن: شماره واحد / همان شماره واحد (رمز پیش‌فرض)")
    print("=" * 55)
    app.run(host="0.0.0.0", port=5000, debug=False)
