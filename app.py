# -*- coding: utf-8 -*-
"""
سیستم مدیریت مالی ساختمان - نسخه تک‌فایل (بدون نیاز به پوشه templates)
"""
import os
from functools import wraps
from io import BytesIO

from flask import (
    Flask, request, redirect, url_for,
    flash, session, send_file
)
from jinja2 import DictLoader, Environment, select_autoescape
import jdatetime

from database import (
    get_setting, set_setting, get_current_rates, get_all_units, get_unit,
    update_unit, add_transaction, get_transactions, get_fund_summary,
    get_monthly_unit_report, add_rate, get_rate_history, delete_transaction,
    verify_admin, verify_resident, set_unit_password, set_admin_password,
    get_pending_payments, confirm_transaction, reject_transaction,
    get_unit_status, DB_PATH
)

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

TEMPLATES = {
    "base.html": "<!DOCTYPE html>\n<html lang=\"fa\" dir=\"rtl\">\n<head>\n<meta charset=\"UTF-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n<title>{% block title %}مدیریت مالی ساختمان{% endblock %}</title>\n<link href=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css\" rel=\"stylesheet\">\n<link href=\"https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css\" rel=\"stylesheet\">\n<style>\n:root { --primary: #1F4E79; }\nbody { font-family: Tahoma, \"Segoe UI\", sans-serif; background: #f0f2f5; min-height: 100vh; }\n.sidebar {\n  width: 250px; background: linear-gradient(180deg, #1F4E79, #163a5f);\n  min-height: 100vh; position: fixed; right: 0; top: 0; color: #fff; z-index: 100;\n  box-shadow: -2px 0 12px rgba(0,0,0,.12);\n}\n.sidebar .brand { padding: 1.2rem 1rem; font-weight: 700; font-size: 1.05rem; border-bottom: 1px solid rgba(255,255,255,.15); line-height: 1.4; }\n.sidebar .brand small { display: block; font-weight: 400; font-size: .75rem; opacity: .8; margin-top: 3px; }\n.sidebar .nav-link { color: rgba(255,255,255,.88); padding: .7rem 1.15rem; font-size: .92rem; }\n.sidebar .nav-link:hover, .sidebar .nav-link.active { background: rgba(255,255,255,.12); color: #fff; }\n.sidebar .nav-link i { margin-left: 8px; width: 20px; text-align: center; }\n.main { margin-right: 250px; padding: 1.3rem 1.5rem; }\n.card { border: none; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,.06); }\n.card-header { background: #fff; border-bottom: 1px solid #eee; font-weight: 600; border-radius: 12px 12px 0 0 !important; }\n.kpi { border-radius: 12px; padding: 1.1rem 1.2rem; color: #fff; height: 100%; }\n.kpi .label { font-size: .85rem; opacity: .9; }\n.kpi .value { font-size: 1.35rem; font-weight: 700; margin-top: .2rem; }\n.kpi-blue { background: linear-gradient(135deg, #2E75B6, #1F4E79); }\n.kpi-green { background: linear-gradient(135deg, #28a745, #1e7e34); }\n.kpi-orange { background: linear-gradient(135deg, #fd7e14, #e8590c); }\n.kpi-purple { background: linear-gradient(135deg, #6f42c1, #5a32a3); }\n.kpi-red { background: linear-gradient(135deg, #dc3545, #b02a37); }\n.table th { background: #1F4E79 !important; color: #fff !important; font-weight: 500; font-size: .85rem; white-space: nowrap; }\n.table td { vertical-align: middle; font-size: .88rem; }\n.btn-primary { background: #1F4E79; border-color: #1F4E79; }\n.btn-primary:hover { background: #163a5f; border-color: #163a5f; }\n.page-title { font-size: 1.3rem; font-weight: 700; color: #1F4E79; margin-bottom: 1rem; }\n.badge-debt { background: #dc3545; }\n.badge-ok { background: #198754; }\n@media (max-width: 768px) {\n  .sidebar { width: 100%; min-height: auto; position: relative; }\n  .main { margin-right: 0; }\n}\n</style>\n{% block extra_css %}{% endblock %}\n</head>\n<body>\n{% if user.role %}\n<div class=\"sidebar d-flex flex-column\">\n  <div class=\"brand\">\n    {{ building_name }}\n    <small>\n      {% if user.role == 'admin' %}پنل مدیر{% else %}واحد {{ user.unit_number }}{% endif %}\n    </small>\n  </div>\n  <nav class=\"nav flex-column mt-2 flex-grow-1\">\n    {% if user.role == 'admin' %}\n      <a class=\"nav-link {% if request.endpoint == 'admin_dashboard' %}active{% endif %}\" href=\"{{ url_for('admin_dashboard') }}\"><i class=\"bi bi-speedometer2\"></i> داشبورد</a>\n      <a class=\"nav-link {% if request.endpoint == 'admin_pending' %}active{% endif %}\" href=\"{{ url_for('admin_pending') }}\"><i class=\"bi bi-hourglass-split\"></i> واریزی‌های در انتظار</a>\n      <a class=\"nav-link {% if request.endpoint == 'admin_units' %}active{% endif %}\" href=\"{{ url_for('admin_units') }}\"><i class=\"bi bi-houses\"></i> واحدها و رمزها</a>\n      <a class=\"nav-link {% if 'transaction' in (request.endpoint or '') %}active{% endif %}\" href=\"{{ url_for('admin_transactions') }}\"><i class=\"bi bi-cash-stack\"></i> تراکنش‌ها</a>\n      <a class=\"nav-link {% if request.endpoint == 'admin_report' %}active{% endif %}\" href=\"{{ url_for('admin_report') }}\"><i class=\"bi bi-bar-chart-line\"></i> گزارش ماهانه</a>\n      <a class=\"nav-link {% if request.endpoint == 'admin_settings' %}active{% endif %}\" href=\"{{ url_for('admin_settings') }}\"><i class=\"bi bi-gear\"></i> تنظیمات</a>\n    {% else %}\n      <a class=\"nav-link {% if request.endpoint == 'resident_dashboard' %}active{% endif %}\" href=\"{{ url_for('resident_dashboard') }}\"><i class=\"bi bi-house\"></i> وضعیت من</a>\n      <a class=\"nav-link {% if request.endpoint == 'resident_payment' %}active{% endif %}\" href=\"{{ url_for('resident_payment') }}\"><i class=\"bi bi-send\"></i> اعلام واریزی</a>\n      <a class=\"nav-link {% if request.endpoint == 'resident_history' %}active{% endif %}\" href=\"{{ url_for('resident_history') }}\"><i class=\"bi bi-clock-history\"></i> تاریخچه من</a>\n    {% endif %}\n  </nav>\n  <div class=\"p-3 border-top border-secondary\">\n    <div class=\"small opacity-75 mb-2\">امروز: {{ today_jalali }}</div>\n    <a href=\"{{ url_for('logout') }}\" class=\"btn btn-sm btn-outline-light w-100\"><i class=\"bi bi-box-arrow-right\"></i> خروج</a>\n  </div>\n</div>\n{% endif %}\n\n<div class=\"{% if user.role %}main{% else %}container py-4{% endif %}\">\n  {% with messages = get_flashed_messages(with_categories=true) %}\n    {% if messages %}\n      {% for cat, msg in messages %}\n        <div class=\"alert alert-{{ cat }} alert-dismissible fade show\" role=\"alert\">\n          {{ msg }}\n          <button type=\"button\" class=\"btn-close\" data-bs-dismiss=\"alert\"></button>\n        </div>\n      {% endfor %}\n    {% endif %}\n  {% endwith %}\n  {% block content %}{% endblock %}\n</div>\n<script src=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js\"></script>\n{% block extra_js %}{% endblock %}\n</body>\n</html>\n",
    "login.html": "{% extends \"base.html\" %}\n{% block title %}ورود - مدیریت مالی ساختمان{% endblock %}\n\n{% block content %}\n<div class=\"row justify-content-center mt-4\">\n  <div class=\"col-md-5\">\n    <div class=\"text-center mb-4\">\n      <h3 style=\"color:#1F4E79;\">{{ building_name }}</h3>\n      <p class=\"text-muted\">سیستم مدیریت مالی ساختمان</p>\n    </div>\n\n    <div class=\"card shadow-sm\">\n      <div class=\"card-body p-4\">\n        <ul class=\"nav nav-tabs nav-fill mb-3\" role=\"tablist\">\n          <li class=\"nav-item\">\n            <button class=\"nav-link active\" data-bs-toggle=\"tab\" data-bs-target=\"#tab-resident\" type=\"button\">ورود ساکن</button>\n          </li>\n          <li class=\"nav-item\">\n            <button class=\"nav-link\" data-bs-toggle=\"tab\" data-bs-target=\"#tab-admin\" type=\"button\">ورود مدیر</button>\n          </li>\n        </ul>\n\n        <div class=\"tab-content\">\n          <!-- ساکن -->\n          <div class=\"tab-pane fade show active\" id=\"tab-resident\">\n            <form method=\"post\">\n              <input type=\"hidden\" name=\"role\" value=\"resident\">\n              <div class=\"mb-3\">\n                <label class=\"form-label\">شماره واحد</label>\n                <input type=\"text\" name=\"unit_number\" class=\"form-control form-control-lg\" placeholder=\"مثلاً 101\" required autofocus>\n              </div>\n              <div class=\"mb-3\">\n                <label class=\"form-label\">رمز عبور</label>\n                <input type=\"password\" name=\"password\" class=\"form-control form-control-lg\" placeholder=\"رمز عبور واحد\" required>\n              </div>\n              <button type=\"submit\" class=\"btn btn-primary w-100 btn-lg\">ورود به پنل ساکن</button>\n            </form>\n            <p class=\"text-muted small mt-3 mb-0 text-center\">\n              رمز پیش‌فرض هر واحد = همان شماره واحد است<br>\n              (مثلاً واحد ۱۰۱ با رمز ۱۰۱ وارد شود)\n            </p>\n          </div>\n\n          <!-- مدیر -->\n          <div class=\"tab-pane fade\" id=\"tab-admin\">\n            <form method=\"post\">\n              <input type=\"hidden\" name=\"role\" value=\"admin\">\n              <div class=\"mb-3\">\n                <label class=\"form-label\">نام کاربری مدیر</label>\n                <input type=\"text\" name=\"username\" class=\"form-control form-control-lg\" value=\"admin\" required>\n              </div>\n              <div class=\"mb-3\">\n                <label class=\"form-label\">رمز عبور</label>\n                <input type=\"password\" name=\"password\" class=\"form-control form-control-lg\" required>\n              </div>\n              <button type=\"submit\" class=\"btn btn-dark w-100 btn-lg\">ورود مدیر</button>\n            </form>\n            <p class=\"text-muted small mt-3 mb-0 text-center\">\n              پیش‌فرض: admin / admin123<br>\n              (حتماً بعد از ورود اول رمز را عوض کنید)\n            </p>\n          </div>\n        </div>\n      </div>\n    </div>\n  </div>\n</div>\n{% endblock %}\n",
    "admin/dashboard.html": "{% extends \"base.html\" %}\n{% block title %}داشبورد مدیر{% endblock %}\n\n{% block content %}\n<div class=\"page-title\"><i class=\"bi bi-speedometer2\"></i> داشبورد مدیر</div>\n\n{% if pending %}\n<div class=\"alert alert-warning d-flex justify-content-between align-items-center\">\n  <span><i class=\"bi bi-hourglass-split\"></i> <strong>{{ pending|length }}</strong> واریزی در انتظار تأیید دارید.</span>\n  <a href=\"{{ url_for('admin_pending') }}\" class=\"btn btn-sm btn-warning\">مشاهده و تأیید</a>\n</div>\n{% endif %}\n\n<div class=\"row g-3 mb-4\">\n  <div class=\"col-md-3\"><div class=\"kpi kpi-blue\"><div class=\"label\">صندوق جاری</div><div class=\"value\">{{ format_money(funds.current_fund) }}</div><small>ریال</small></div></div>\n  <div class=\"col-md-3\"><div class=\"kpi kpi-green\"><div class=\"label\">صندوق مالکانه</div><div class=\"value\">{{ format_money(funds.ownership_fund) }}</div><small>ریال</small></div></div>\n  <div class=\"col-md-3\"><div class=\"kpi kpi-orange\"><div class=\"label\">جمع کل موجودی</div><div class=\"value\">{{ format_money(funds.total_fund) }}</div><small>ریال</small></div></div>\n  <div class=\"col-md-3\"><div class=\"kpi kpi-purple\"><div class=\"label\">نرخ شارژ ماهانه</div><div class=\"value\">{{ format_money(rates.monthly_charge) }}</div><small>ریال</small></div></div>\n</div>\n\n<div class=\"row g-3\">\n  <div class=\"col-lg-8\">\n    <div class=\"card\">\n      <div class=\"card-header d-flex justify-content-between\">\n        <span>آخرین تراکنش‌ها</span>\n        <a href=\"{{ url_for('admin_transactions') }}\" class=\"btn btn-sm btn-outline-primary\">همه</a>\n      </div>\n      <div class=\"card-body p-0\">\n        <table class=\"table table-hover mb-0\">\n          <thead><tr><th>تاریخ</th><th>واحد</th><th>نوع</th><th>مبلغ</th><th>وضعیت</th></tr></thead>\n          <tbody>\n            {% for t in recent %}\n            <tr>\n              <td>{{ t.jalali_date }}</td>\n              <td>{{ t.unit_number or '—' }}</td>\n              <td>\n                {% if 'ماهانه' in t.trans_type %}<span class=\"badge bg-primary\">{{ t.trans_type }}</span>\n                {% elif 'مالکانه' in t.trans_type %}<span class=\"badge bg-success\">{{ t.trans_type }}</span>\n                {% elif t.trans_type == 'هزینه' %}<span class=\"badge bg-danger\">{{ t.trans_type }}</span>\n                {% else %}<span class=\"badge bg-secondary\">{{ t.trans_type }}</span>{% endif %}\n              </td>\n              <td class=\"fw-semibold\">{{ format_money(t.amount) }}</td>\n              <td>\n                {% if t.status == 'pending' %}<span class=\"badge bg-warning text-dark\">در انتظار</span>\n                {% elif t.status == 'confirmed' %}<span class=\"badge bg-success\">تأیید شده</span>\n                {% else %}<span class=\"badge bg-secondary\">{{ t.status }}</span>{% endif %}\n              </td>\n            </tr>\n            {% else %}\n            <tr><td colspan=\"5\" class=\"text-center text-muted py-4\">تراکنشی نیست</td></tr>\n            {% endfor %}\n          </tbody>\n        </table>\n      </div>\n    </div>\n  </div>\n  <div class=\"col-lg-4\">\n    <div class=\"card\">\n      <div class=\"card-header\">دسترسی سریع</div>\n      <div class=\"card-body d-grid gap-2\">\n        <a href=\"{{ url_for('admin_pending') }}\" class=\"btn btn-warning\"><i class=\"bi bi-hourglass-split\"></i> تأیید واریزی‌ها</a>\n        <a href=\"{{ url_for('admin_transactions') }}\" class=\"btn btn-primary\"><i class=\"bi bi-plus-circle\"></i> ثبت تراکنش</a>\n        <a href=\"{{ url_for('admin_report') }}\" class=\"btn btn-outline-primary\"><i class=\"bi bi-file-earmark-bar-graph\"></i> گزارش ماهانه</a>\n        <a href=\"{{ url_for('admin_units') }}\" class=\"btn btn-outline-secondary\"><i class=\"bi bi-key\"></i> مدیریت رمز واحدها</a>\n      </div>\n    </div>\n  </div>\n</div>\n{% endblock %}\n",
    "admin/pending.html": "{% extends \"base.html\" %}\n{% block title %}واریزی‌های در انتظار{% endblock %}\n\n{% block content %}\n<div class=\"page-title\"><i class=\"bi bi-hourglass-split\"></i> واریزی‌های در انتظار تأیید</div>\n\n{% if not pending %}\n<div class=\"alert alert-success\">در حال حاضر هیچ واریزی در انتظاری وجود ندارد.</div>\n{% else %}\n<div class=\"card\">\n  <div class=\"card-body p-0\">\n    <table class=\"table table-hover mb-0\">\n      <thead>\n        <tr>\n          <th>تاریخ اعلام</th>\n          <th>واحد</th>\n          <th>نوع</th>\n          <th>مبلغ</th>\n          <th>کد پیگیری</th>\n          <th>توضیح</th>\n          <th>عملیات</th>\n        </tr>\n      </thead>\n      <tbody>\n        {% for t in pending %}\n        <tr>\n          <td>{{ t.jalali_date }}<br><small class=\"text-muted\">{{ t.month }} {{ t.year }}</small></td>\n          <td class=\"fw-bold\">{{ t.unit_number }}</td>\n          <td>\n            {% if 'ماهانه' in t.trans_type %}<span class=\"badge bg-primary\">{{ t.trans_type }}</span>\n            {% else %}<span class=\"badge bg-success\">{{ t.trans_type }}</span>{% endif %}\n          </td>\n          <td class=\"fw-semibold\">{{ format_money(t.amount) }}</td>\n          <td><code>{{ t.tracking_code or '—' }}</code></td>\n          <td class=\"small\">{{ t.description or '—' }}</td>\n          <td>\n            <form method=\"post\" action=\"{{ url_for('admin_pending_confirm', trans_id=t.id) }}\" class=\"d-inline\">\n              <button type=\"submit\" class=\"btn btn-sm btn-success\" onclick=\"return confirm('تأیید این واریزی؟')\">تأیید</button>\n            </form>\n            <form method=\"post\" action=\"{{ url_for('admin_pending_reject', trans_id=t.id) }}\" class=\"d-inline\">\n              <button type=\"submit\" class=\"btn btn-sm btn-outline-danger\" onclick=\"return confirm('رد کردن این واریزی؟')\">رد</button>\n            </form>\n          </td>\n        </tr>\n        {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</div>\n{% endif %}\n{% endblock %}\n",
    "admin/report.html": "{% extends \"base.html\" %}\n{% block title %}گزارش ماهانه{% endblock %}\n\n{% block content %}\n<div class=\"d-flex justify-content-between align-items-center flex-wrap gap-2 mb-3\">\n  <div class=\"page-title mb-0\"><i class=\"bi bi-bar-chart-line\"></i> گزارش ماهانه</div>\n  <a href=\"{{ url_for('admin_report_pdf', year=year, month=month) }}\" class=\"btn btn-danger\"><i class=\"bi bi-file-earmark-pdf\"></i> دانلود PDF</a>\n</div>\n\n<div class=\"card mb-3\">\n  <div class=\"card-body py-3\">\n    <form method=\"get\" class=\"row g-2 align-items-end\">\n      <div class=\"col-auto\">\n        <label class=\"form-label mb-1\">سال</label>\n        <select name=\"year\" class=\"form-select\">{% for y in range(1404,1409) %}<option value=\"{{ y }}\" {% if y==year %}selected{% endif %}>{{ y }}</option>{% endfor %}</select>\n      </div>\n      <div class=\"col-auto\">\n        <label class=\"form-label mb-1\">ماه</label>\n        <select name=\"month\" class=\"form-select\">{% for m in persian_months %}<option value=\"{{ m }}\" {% if m==month %}selected{% endif %}>{{ m }}</option>{% endfor %}</select>\n      </div>\n      <div class=\"col-auto\"><button class=\"btn btn-primary\">نمایش</button></div>\n    </form>\n  </div>\n</div>\n\n<div class=\"row g-3 mb-3\">\n  <div class=\"col-md-3\"><div class=\"card text-center p-3\"><div class=\"text-muted small\">پرداخت ماهانه</div><div class=\"fs-5 fw-bold text-primary\">{{ format_money(report.total_paid_monthly) }}</div></div></div>\n  <div class=\"col-md-3\"><div class=\"card text-center p-3\"><div class=\"text-muted small\">پرداخت مالکانه</div><div class=\"fs-5 fw-bold text-success\">{{ format_money(report.total_paid_ownership) }}</div></div></div>\n  <div class=\"col-md-3\"><div class=\"card text-center p-3\"><div class=\"text-muted small\">بدهی ماهانه</div><div class=\"fs-5 fw-bold text-danger\">{{ format_money(report.total_debt_monthly) }}</div></div></div>\n  <div class=\"col-md-3\"><div class=\"card text-center p-3\"><div class=\"text-muted small\">هزینه‌ها</div><div class=\"fs-5 fw-bold text-warning\">{{ format_money(report.expenses) }}</div></div></div>\n</div>\n\n<div class=\"card\">\n  <div class=\"card-header\">وضعیت واحدها — {{ month }} {{ year }}</div>\n  <div class=\"card-body p-0\">\n    <div class=\"table-responsive\">\n      <table class=\"table table-sm table-hover mb-0\">\n        <thead>\n          <tr>\n            <th>واحد</th><th>مالک</th>\n            <th>مورد انتظار ماهانه</th><th>پرداخت</th><th>بدهی</th>\n            <th>مورد انتظار مالکانه</th><th>پرداخت</th><th>بدهی</th>\n          </tr>\n        </thead>\n        <tbody>\n          {% for u in report.units %}\n          <tr>\n            <td class=\"fw-bold\">{{ u.unit_number }}</td>\n            <td class=\"small\">{{ u.owner_name or '—' }}</td>\n            <td>{{ format_money(u.expected_monthly) }}</td>\n            <td>{{ format_money(u.paid_monthly) }}</td>\n            <td>{% if u.debt_monthly > 0 %}<span class=\"badge badge-debt\">{{ format_money(u.debt_monthly) }}</span>{% else %}<span class=\"badge badge-ok\">۰</span>{% endif %}</td>\n            <td>{{ format_money(u.expected_ownership) }}</td>\n            <td>{{ format_money(u.paid_ownership) }}</td>\n            <td>{% if u.debt_ownership > 0 %}<span class=\"badge badge-debt\">{{ format_money(u.debt_ownership) }}</span>{% else %}<span class=\"badge badge-ok\">۰</span>{% endif %}</td>\n          </tr>\n          {% endfor %}\n        </tbody>\n      </table>\n    </div>\n  </div>\n</div>\n{% endblock %}\n",
    "admin/settings.html": "{% extends \"base.html\" %}\n{% block title %}تنظیمات{% endblock %}\n\n{% block content %}\n<div class=\"page-title\"><i class=\"bi bi-gear\"></i> تنظیمات</div>\n\n<div class=\"row g-3\">\n  <div class=\"col-lg-6\">\n    <div class=\"card\">\n      <div class=\"card-header\">نرخ‌های جاری</div>\n      <div class=\"card-body\">\n        <div class=\"alert alert-info py-2\">\n          فعلی: ماهانه <strong>{{ format_money(rates.monthly_charge) }}</strong> |\n          مالکانه <strong>{{ format_money(rates.ownership_charge) }}</strong>\n          <br><small>{{ rates.effective_date }}</small>\n        </div>\n        <form method=\"post\">\n          <input type=\"hidden\" name=\"action\" value=\"rates\">\n          <div class=\"mb-2\"><label class=\"form-label\">شارژ ماهانه جدید</label><input type=\"text\" name=\"monthly_charge\" class=\"form-control\" value=\"{{ rates.monthly_charge }}\" required></div>\n          <div class=\"mb-2\"><label class=\"form-label\">شارژ مالکانه جدید</label><input type=\"text\" name=\"ownership_charge\" class=\"form-control\" value=\"{{ rates.ownership_charge }}\" required></div>\n          <div class=\"mb-2\"><label class=\"form-label\">تاریخ اعمال</label><input type=\"text\" name=\"effective_date\" class=\"form-control\" value=\"{{ today_jalali }}\" required></div>\n          <div class=\"mb-2\"><label class=\"form-label\">دلیل</label><input type=\"text\" name=\"reason\" class=\"form-control\"></div>\n          <button class=\"btn btn-primary\">ثبت نرخ جدید</button>\n        </form>\n      </div>\n    </div>\n  </div>\n  <div class=\"col-lg-6\">\n    <div class=\"card mb-3\">\n      <div class=\"card-header\">تنظیمات عمومی</div>\n      <div class=\"card-body\">\n        <form method=\"post\">\n          <input type=\"hidden\" name=\"action\" value=\"general\">\n          <div class=\"mb-2\"><label class=\"form-label\">نام ساختمان</label><input type=\"text\" name=\"building_name\" class=\"form-control\" value=\"{{ building_name }}\"></div>\n          <div class=\"mb-2\"><label class=\"form-label\">مانده اولیه صندوق جاری</label><input type=\"text\" name=\"initial_current_fund\" class=\"form-control\" value=\"{{ initial_current }}\"></div>\n          <div class=\"mb-2\"><label class=\"form-label\">مانده اولیه صندوق مالکانه</label><input type=\"text\" name=\"initial_ownership_fund\" class=\"form-control\" value=\"{{ initial_ownership }}\"></div>\n          <button class=\"btn btn-primary\">ذخیره</button>\n        </form>\n      </div>\n    </div>\n    <div class=\"card\">\n      <div class=\"card-header\">تغییر رمز مدیر</div>\n      <div class=\"card-body\">\n        <form method=\"post\">\n          <input type=\"hidden\" name=\"action\" value=\"admin_password\">\n          <div class=\"mb-2\"><label class=\"form-label\">رمز جدید</label><input type=\"password\" name=\"new_password\" class=\"form-control\" required></div>\n          <div class=\"mb-2\"><label class=\"form-label\">تکرار رمز</label><input type=\"password\" name=\"new_password2\" class=\"form-control\" required></div>\n          <button class=\"btn btn-dark\">تغییر رمز</button>\n        </form>\n      </div>\n    </div>\n  </div>\n</div>\n\n<div class=\"card mt-3\">\n  <div class=\"card-header\">تاریخچه نرخ‌ها</div>\n  <div class=\"card-body p-0\">\n    <table class=\"table table-sm mb-0\">\n      <thead><tr><th>تاریخ</th><th>ماهانه</th><th>مالکانه</th><th>دلیل</th></tr></thead>\n      <tbody>\n        {% for h in history %}\n        <tr><td>{{ h.effective_date }}</td><td>{{ format_money(h.monthly_charge) }}</td><td>{{ format_money(h.ownership_charge) }}</td><td>{{ h.reason }}</td></tr>\n        {% else %}\n        <tr><td colspan=\"4\" class=\"text-center text-muted\">سابقه‌ای نیست</td></tr>\n        {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</div>\n{% endblock %}\n",
    "admin/transactions.html": "{% extends \"base.html\" %}\n{% block title %}تراکنش‌ها{% endblock %}\n\n{% block content %}\n<div class=\"page-title\"><i class=\"bi bi-cash-stack\"></i> ثبت و مدیریت تراکنش‌ها</div>\n\n<div class=\"row g-3\">\n  <div class=\"col-lg-4\">\n    <div class=\"card\">\n      <div class=\"card-header bg-primary text-white\">ثبت تراکنش (تأییدشده)</div>\n      <div class=\"card-body\">\n        <form method=\"post\" action=\"{{ url_for('admin_transactions_add') }}\">\n          <div class=\"mb-2\">\n            <label class=\"form-label\">تاریخ شمسی</label>\n            <input type=\"text\" name=\"jalali_date\" class=\"form-control\" value=\"{{ today_jalali }}\" required>\n          </div>\n          <div class=\"row mb-2\">\n            <div class=\"col-6\">\n              <label class=\"form-label\">سال</label>\n              <select name=\"year\" class=\"form-select\">\n                {% for y in range(1404,1409) %}<option value=\"{{ y }}\" {% if y==1405 %}selected{% endif %}>{{ y }}</option>{% endfor %}\n              </select>\n            </div>\n            <div class=\"col-6\">\n              <label class=\"form-label\">ماه</label>\n              <select name=\"month\" class=\"form-select\">\n                {% for m in persian_months %}<option value=\"{{ m }}\" {% if m=='آبان' %}selected{% endif %}>{{ m }}</option>{% endfor %}\n              </select>\n            </div>\n          </div>\n          <div class=\"mb-2\">\n            <label class=\"form-label\">نوع</label>\n            <select name=\"trans_type\" class=\"form-select\" id=\"adminType\">\n              <option value=\"پرداخت شارژ ماهانه\">پرداخت شارژ ماهانه</option>\n              <option value=\"پرداخت شارژ مالکانه\">پرداخت شارژ مالکانه</option>\n              <option value=\"هزینه\">هزینه</option>\n              <option value=\"سایر درآمد\">سایر درآمد</option>\n            </select>\n          </div>\n          <div class=\"mb-2\" id=\"adminUnitGroup\">\n            <label class=\"form-label\">واحد</label>\n            <select name=\"unit_number\" class=\"form-select\">\n              <option value=\"\">—</option>\n              {% for u in units %}<option value=\"{{ u.unit_number }}\">{{ u.unit_number }}</option>{% endfor %}\n            </select>\n          </div>\n          <div class=\"mb-2\">\n            <label class=\"form-label\">مبلغ</label>\n            <input type=\"text\" name=\"amount\" class=\"form-control\" id=\"adminAmount\" value=\"{{ rates.monthly_charge }}\" required>\n          </div>\n          <div class=\"mb-2\">\n            <label class=\"form-label\">کد پیگیری</label>\n            <input type=\"text\" name=\"tracking_code\" class=\"form-control\">\n          </div>\n          <div class=\"mb-2\">\n            <label class=\"form-label\">توضیحات / دسته‌بندی</label>\n            <input type=\"text\" name=\"description\" class=\"form-control\">\n            <input type=\"hidden\" name=\"category\" value=\"\">\n          </div>\n          <button type=\"submit\" class=\"btn btn-primary w-100\">ثبت</button>\n        </form>\n      </div>\n    </div>\n  </div>\n  <div class=\"col-lg-8\">\n    <div class=\"card\">\n      <div class=\"card-header d-flex justify-content-between flex-wrap gap-2\">\n        <span>لیست تراکنش‌ها</span>\n        <form class=\"d-flex gap-1\" method=\"get\">\n          <select name=\"year\" class=\"form-select form-select-sm\" style=\"width:90px\">\n            <option value=\"\">سال</option>\n            {% for y in range(1404,1409) %}<option value=\"{{ y }}\" {% if selected_year==y %}selected{% endif %}>{{ y }}</option>{% endfor %}\n          </select>\n          <select name=\"month\" class=\"form-select form-select-sm\" style=\"width:100px\">\n            <option value=\"\">ماه</option>\n            {% for m in persian_months %}<option value=\"{{ m }}\" {% if selected_month==m %}selected{% endif %}>{{ m }}</option>{% endfor %}\n          </select>\n          <select name=\"status\" class=\"form-select form-select-sm\" style=\"width:110px\">\n            <option value=\"\">همه وضعیت‌ها</option>\n            <option value=\"confirmed\" {% if selected_status=='confirmed' %}selected{% endif %}>تأیید شده</option>\n            <option value=\"pending\" {% if selected_status=='pending' %}selected{% endif %}>در انتظار</option>\n            <option value=\"rejected\" {% if selected_status=='rejected' %}selected{% endif %}>رد شده</option>\n          </select>\n          <button class=\"btn btn-sm btn-outline-primary\">فیلتر</button>\n        </form>\n      </div>\n      <div class=\"card-body p-0\" style=\"max-height:520px;overflow:auto;\">\n        <table class=\"table table-sm table-hover mb-0\">\n          <thead class=\"sticky-top\"><tr><th>#</th><th>تاریخ</th><th>واحد</th><th>نوع</th><th>مبلغ</th><th>وضعیت</th><th></th></tr></thead>\n          <tbody>\n            {% for t in transactions %}\n            <tr>\n              <td>{{ t.id }}</td>\n              <td>{{ t.jalali_date }}</td>\n              <td>{{ t.unit_number or '—' }}</td>\n              <td class=\"small\">{{ t.trans_type }}</td>\n              <td>{{ format_money(t.amount) }}</td>\n              <td>\n                {% if t.status=='pending' %}<span class=\"badge bg-warning text-dark\">در انتظار</span>\n                {% elif t.status=='confirmed' %}<span class=\"badge bg-success\">تأیید</span>\n                {% else %}<span class=\"badge bg-secondary\">{{ t.status }}</span>{% endif %}\n              </td>\n              <td>\n                <form method=\"post\" action=\"{{ url_for('admin_transactions_delete', trans_id=t.id) }}\" onsubmit=\"return confirm('حذف؟')\">\n                  <button class=\"btn btn-sm btn-outline-danger py-0\">×</button>\n                </form>\n              </td>\n            </tr>\n            {% else %}\n            <tr><td colspan=\"7\" class=\"text-center text-muted py-4\">موردی نیست</td></tr>\n            {% endfor %}\n          </tbody>\n        </table>\n      </div>\n    </div>\n  </div>\n</div>\n{% endblock %}\n{% block extra_js %}\n<script>\ndocument.getElementById('adminType').addEventListener('change', function() {\n  document.getElementById('adminUnitGroup').style.display = this.value === 'هزینه' ? 'none' : 'block';\n  const a = document.getElementById('adminAmount');\n  if (this.value === 'پرداخت شارژ ماهانه') a.value = '{{ rates.monthly_charge }}';\n  else if (this.value === 'پرداخت شارژ مالکانه') a.value = '{{ rates.ownership_charge }}';\n  else a.value = '';\n});\n</script>\n{% endblock %}\n",
    "admin/units.html": "{% extends \"base.html\" %}\n{% block title %}واحدها و رمزها{% endblock %}\n\n{% block content %}\n<div class=\"page-title\"><i class=\"bi bi-houses\"></i> مدیریت واحدها و رمز عبور</div>\n<p class=\"text-muted\">رمز پیش‌فرض هر واحد = شماره واحد است. می‌توانید رمز جدید برای هر واحد تنظیم کنید.</p>\n\n<div class=\"card\">\n  <div class=\"card-body p-0\">\n    <div class=\"table-responsive\">\n      <table class=\"table table-hover mb-0\">\n        <thead>\n          <tr>\n            <th>واحد</th><th>طبقه</th><th>نام مالک</th><th>تلفن</th><th>وضعیت</th>\n            <th>توضیحات</th><th>رمز جدید</th><th></th>\n          </tr>\n        </thead>\n        <tbody>\n          {% for u in units %}\n          <tr>\n            <form method=\"post\" action=\"{{ url_for('admin_units_update') }}\">\n              <input type=\"hidden\" name=\"unit_number\" value=\"{{ u.unit_number }}\">\n              <td class=\"fw-bold\">{{ u.unit_number }}</td>\n              <td>{{ u.floor }}</td>\n              <td><input type=\"text\" name=\"owner_name\" class=\"form-control form-control-sm\" value=\"{{ u.owner_name }}\"></td>\n              <td><input type=\"text\" name=\"phone\" class=\"form-control form-control-sm\" value=\"{{ u.phone }}\"></td>\n              <td>\n                <select name=\"status\" class=\"form-select form-select-sm\">\n                  <option value=\"ساکن\" {% if u.status=='ساکن' %}selected{% endif %}>ساکن</option>\n                  <option value=\"خالی\" {% if u.status=='خالی' %}selected{% endif %}>خالی</option>\n                  <option value=\"اجاره‌ای\" {% if u.status=='اجاره‌ای' %}selected{% endif %}>اجاره‌ای</option>\n                </select>\n              </td>\n              <td><input type=\"text\" name=\"notes\" class=\"form-control form-control-sm\" value=\"{{ u.notes }}\"></td>\n              <td><input type=\"text\" name=\"new_password\" class=\"form-control form-control-sm\" placeholder=\"خالی = بدون تغییر\"></td>\n              <td><button type=\"submit\" class=\"btn btn-sm btn-primary\">ذخیره</button></td>\n            </form>\n          </tr>\n          {% endfor %}\n        </tbody>\n      </table>\n    </div>\n  </div>\n</div>\n{% endblock %}\n",
    "resident/dashboard.html": "{% extends \"base.html\" %}\n{% block title %}وضعیت من - واحد {{ user.unit_number }}{% endblock %}\n\n{% block content %}\n<div class=\"page-title\">وضعیت واحد {{ user.unit_number }}</div>\n\n{% if unit and unit.owner_name %}\n<p class=\"text-muted\">مالک / ساکن: <strong>{{ unit.owner_name }}</strong></p>\n{% endif %}\n\n<div class=\"row g-3 mb-4\">\n  <div class=\"col-md-6\">\n    <div class=\"kpi kpi-blue\">\n      <div class=\"label\">شارژ ماهانه {{ status.month }} {{ status.year }}</div>\n      <div class=\"value\">{{ format_money(status.paid_monthly) }} / {{ format_money(status.expected_monthly) }}</div>\n      <small>\n        {% if status.debt_monthly > 0 %}\n          بدهی: {{ format_money(status.debt_monthly) }} ریال\n        {% else %}\n          تسویه شده ✓\n        {% endif %}\n      </small>\n    </div>\n  </div>\n  <div class=\"col-md-6\">\n    <div class=\"kpi kpi-green\">\n      <div class=\"label\">شارژ مالکانه {{ status.month }} {{ status.year }}</div>\n      <div class=\"value\">{{ format_money(status.paid_ownership) }} / {{ format_money(status.expected_ownership) }}</div>\n      <small>\n        {% if status.debt_ownership > 0 %}\n          بدهی: {{ format_money(status.debt_ownership) }} ریال\n        {% else %}\n          تسویه شده ✓\n        {% endif %}\n      </small>\n    </div>\n  </div>\n</div>\n\n{% if pending %}\n<div class=\"alert alert-warning\">\n  <i class=\"bi bi-hourglass-split\"></i>\n  شما {{ pending|length }} اعلام واریزی در انتظار تأیید مدیر دارید.\n</div>\n{% endif %}\n\n<div class=\"d-grid gap-2 d-md-flex mb-4\">\n  <a href=\"{{ url_for('resident_payment') }}\" class=\"btn btn-primary\"><i class=\"bi bi-send\"></i> اعلام واریزی جدید</a>\n  <a href=\"{{ url_for('resident_history') }}\" class=\"btn btn-outline-primary\"><i class=\"bi bi-clock-history\"></i> مشاهده تاریخچه</a>\n</div>\n\n<div class=\"card\">\n  <div class=\"card-header\">آخرین تراکنش‌های شما</div>\n  <div class=\"card-body p-0\">\n    <table class=\"table table-sm table-hover mb-0\">\n      <thead><tr><th>تاریخ</th><th>نوع</th><th>مبلغ</th><th>کد پیگیری</th><th>وضعیت</th></tr></thead>\n      <tbody>\n        {% for t in transactions[:8] %}\n        <tr>\n          <td>{{ t.jalali_date }}</td>\n          <td>{{ t.trans_type }}</td>\n          <td>{{ format_money(t.amount) }}</td>\n          <td><code>{{ t.tracking_code or '—' }}</code></td>\n          <td>\n            {% if t.status == 'pending' %}<span class=\"badge bg-warning text-dark\">در انتظار تأیید</span>\n            {% elif t.status == 'confirmed' %}<span class=\"badge bg-success\">تأیید شده</span>\n            {% elif t.status == 'rejected' %}<span class=\"badge bg-danger\">رد شده</span>\n            {% else %}<span class=\"badge bg-secondary\">{{ t.status }}</span>{% endif %}\n          </td>\n        </tr>\n        {% else %}\n        <tr><td colspan=\"5\" class=\"text-center text-muted py-3\">هنوز تراکنشی ثبت نشده</td></tr>\n        {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</div>\n{% endblock %}\n",
    "resident/history.html": "{% extends \"base.html\" %}\n{% block title %}تاریخچه پرداخت‌های من{% endblock %}\n\n{% block content %}\n<div class=\"page-title\"><i class=\"bi bi-clock-history\"></i> تاریخچه پرداخت‌های واحد {{ user.unit_number }}</div>\n\n<div class=\"card\">\n  <div class=\"card-body p-0\">\n    <table class=\"table table-hover mb-0\">\n      <thead>\n        <tr><th>تاریخ</th><th>ماه</th><th>نوع</th><th>مبلغ</th><th>کد پیگیری</th><th>وضعیت</th></tr>\n      </thead>\n      <tbody>\n        {% for t in transactions %}\n        <tr>\n          <td>{{ t.jalali_date }}</td>\n          <td>{{ t.month }} {{ t.year }}</td>\n          <td>{{ t.trans_type }}</td>\n          <td class=\"fw-semibold\">{{ format_money(t.amount) }}</td>\n          <td><code>{{ t.tracking_code or '—' }}</code></td>\n          <td>\n            {% if t.status == 'pending' %}<span class=\"badge bg-warning text-dark\">در انتظار</span>\n            {% elif t.status == 'confirmed' %}<span class=\"badge bg-success\">تأیید شده</span>\n            {% elif t.status == 'rejected' %}<span class=\"badge bg-danger\">رد شده</span>\n            {% else %}<span class=\"badge bg-secondary\">{{ t.status }}</span>{% endif %}\n          </td>\n        </tr>\n        {% else %}\n        <tr><td colspan=\"6\" class=\"text-center text-muted py-4\">سابقه‌ای ثبت نشده است</td></tr>\n        {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</div>\n{% endblock %}\n",
    "resident/payment.html": "{% extends \"base.html\" %}\n{% block title %}اعلام واریزی{% endblock %}\n\n{% block content %}\n<div class=\"page-title\"><i class=\"bi bi-send\"></i> اعلام واریزی جدید</div>\n\n<div class=\"row justify-content-center\">\n  <div class=\"col-md-6\">\n    <div class=\"card\">\n      <div class=\"card-body\">\n        <div class=\"alert alert-info\">\n          پس از ثبت، وضعیت «در انتظار تأیید» خواهد بود.\n          مدیر ساختمان پس از بررسی حساب بانکی آن را تأیید می‌کند.\n        </div>\n        <form method=\"post\">\n          <div class=\"mb-3\">\n            <label class=\"form-label\">تاریخ واریز (شمسی)</label>\n            <input type=\"text\" name=\"jalali_date\" class=\"form-control\" value=\"{{ today_jalali }}\" required>\n          </div>\n          <div class=\"row mb-3\">\n            <div class=\"col-6\">\n              <label class=\"form-label\">سال</label>\n              <select name=\"year\" class=\"form-select\" required>\n                {% for y in range(1404, 1409) %}\n                <option value=\"{{ y }}\" {% if y == year %}selected{% endif %}>{{ y }}</option>\n                {% endfor %}\n              </select>\n            </div>\n            <div class=\"col-6\">\n              <label class=\"form-label\">ماه</label>\n              <select name=\"month\" class=\"form-select\" required>\n                {% for m in persian_months %}\n                <option value=\"{{ m }}\" {% if m == month %}selected{% endif %}>{{ m }}</option>\n                {% endfor %}\n              </select>\n            </div>\n          </div>\n          <div class=\"mb-3\">\n            <label class=\"form-label\">نوع پرداخت</label>\n            <select name=\"trans_type\" class=\"form-select\" id=\"payType\" required>\n              <option value=\"پرداخت شارژ ماهانه\">شارژ ماهانه ({{ format_money(rates.monthly_charge) }} ریال)</option>\n              <option value=\"پرداخت شارژ مالکانه\">شارژ مالکانه ({{ format_money(rates.ownership_charge) }} ریال)</option>\n            </select>\n          </div>\n          <div class=\"mb-3\">\n            <label class=\"form-label\">مبلغ واریزی (ریال)</label>\n            <input type=\"text\" name=\"amount\" id=\"payAmount\" class=\"form-control\" value=\"{{ rates.monthly_charge }}\" required>\n          </div>\n          <div class=\"mb-3\">\n            <label class=\"form-label\">کد پیگیری / شماره فیش بانکی</label>\n            <input type=\"text\" name=\"tracking_code\" class=\"form-control\" placeholder=\"مثلاً ۱۲۳۴۵۶۷۸۹۰\" required>\n          </div>\n          <div class=\"mb-3\">\n            <label class=\"form-label\">توضیحات (اختیاری)</label>\n            <input type=\"text\" name=\"description\" class=\"form-control\">\n          </div>\n          <button type=\"submit\" class=\"btn btn-primary w-100\">ثبت اعلام واریزی</button>\n        </form>\n      </div>\n    </div>\n  </div>\n</div>\n{% endblock %}\n\n{% block extra_js %}\n<script>\ndocument.getElementById('payType').addEventListener('change', function() {\n  const amount = document.getElementById('payAmount');\n  if (this.value === 'پرداخت شارژ ماهانه') amount.value = '{{ rates.monthly_charge }}';\n  else amount.value = '{{ rates.ownership_charge }}';\n});\n</script>\n{% endblock %}\n",
}

app.jinja_loader = DictLoader(TEMPLATES)

PERSIAN_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
]

def format_money(amount):
    try:
        return f"{int(amount):,}"
    except Exception:
        return str(amount)

PDF_FONT = "Helvetica"

def fa(text):
    if not text:
        return ""
    return get_display(arabic_reshaper.reshape(str(text)))

_jinja_env = Environment(loader=app.jinja_loader, autoescape=select_autoescape(["html", "xml"]))

def render_template(name, **context):
    context.setdefault("building_name", get_setting("building_name", "مجتمع مسکونی"))
    context.setdefault("today_jalali", jdatetime.date.today().strftime("%Y/%m/%d"))
    context.setdefault("persian_months", PERSIAN_MONTHS)
    context.setdefault("format_money", format_money)
    context.setdefault("user", {
        "role": session.get("role"),
        "username": session.get("username"),
        "unit_number": session.get("unit_number"),
    })
    context.setdefault("request", request)
    context.setdefault("url_for", url_for)
    from flask import get_flashed_messages
    context.setdefault("get_flashed_messages", get_flashed_messages)
    return _jinja_env.get_template(name).render(**context)


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
