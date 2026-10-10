from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import os
import re
from functools import wraps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "firewall.db")

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"
USER_USERNAME = "user"
USER_PASSWORD = "user123"

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"), static_folder=os.path.join(BASE_DIR, "static"))
app.secret_key = "securewall-management-system-secret-key"


def get_connection():
    return sqlite3.connect(DATABASE)


def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT UNIQUE,
            action TEXT,
            enabled INTEGER DEFAULT 1
        )
    """)
    c.execute("PRAGMA table_info(rules)")
    columns = [row[1] for row in c.fetchall()]
    if "enabled" not in columns:
        c.execute("ALTER TABLE rules ADD COLUMN enabled INTEGER DEFAULT 1")
    c.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT,
            result TEXT,
            scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def is_valid_ip(ip):
    pattern = r"^(25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})(\.(25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})){3}$"
    return re.match(pattern, ip) is not None


def scan_ip(ip):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT action FROM rules WHERE ip = ? AND enabled = 1", (ip,))
    rule = c.fetchone()
    result = rule[0] if rule else "ALLOW"
    c.execute("INSERT INTO logs (ip, result) VALUES (?, ?)", (ip, result))
    conn.commit()
    conn.close()
    return result


def admin_required(view_function):
    @wraps(view_function)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Please login as admin first.")
            return redirect(url_for("admin_login"))
        return view_function(*args, **kwargs)
    return wrapper


def user_required(view_function):
    @wraps(view_function)
    def wrapper(*args, **kwargs):
        if not session.get("user_logged_in"):
            flash("Please login as user first.")
            return redirect(url_for("user_login"))
        return view_function(*args, **kwargs)
    return wrapper


init_db()


@app.route("/")
def landing():
    session.pop("admin_logged_in", None)
    session.pop("user_logged_in", None)
    return render_template("landing.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session.clear()
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin username or password.")
    return render_template("login.html", login_type="Admin", post_url=url_for("admin_login"), demo="admin / admin123")


@app.route("/user/login", methods=["GET", "POST"])
def user_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if username == USER_USERNAME and password == USER_PASSWORD:
            session.clear()
            session["user_logged_in"] = True
            return redirect(url_for("user_dashboard"))
        flash("Invalid user username or password.")
    return render_template("login.html", login_type="User", post_url=url_for("user_login"), demo="user / user123")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, ip, action, enabled FROM rules ORDER BY id DESC")
    rules_data = c.fetchall()
    c.execute("SELECT id, ip, result, scanned_at FROM logs ORDER BY id DESC LIMIT 10")
    recent_logs = c.fetchall()
    conn.close()
    return render_template("admin_dashboard.html", rules=rules_data, logs=recent_logs)


@app.route("/admin/rules/add", methods=["POST"])
@admin_required
def add_rule():
    ip = request.form.get("ip", "").strip()
    action = request.form.get("action", "ALLOW").strip().upper()
    if not is_valid_ip(ip):
        flash("Please enter a valid IP address.")
        return redirect(url_for("admin_dashboard"))
    if action not in ["ALLOW", "BLOCK"]:
        flash("Invalid action.")
        return redirect(url_for("admin_dashboard"))
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO rules (ip, action, enabled) VALUES (?, ?, 1)", (ip, action))
    conn.commit()
    conn.close()
    flash("Rule added successfully.")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/rules/edit/<int:rule_id>", methods=["GET", "POST"])
@admin_required
def edit_rule(rule_id):
    conn = get_connection()
    c = conn.cursor()
    if request.method == "POST":
        ip = request.form.get("ip", "").strip()
        action = request.form.get("action", "ALLOW").strip().upper()
        enabled = 1 if request.form.get("enabled") == "on" else 0
        if not is_valid_ip(ip):
            conn.close()
            flash("Please enter a valid IP address.")
            return redirect(url_for("edit_rule", rule_id=rule_id))
        c.execute("UPDATE rules SET ip = ?, action = ?, enabled = ? WHERE id = ?", (ip, action, enabled, rule_id))
        conn.commit()
        conn.close()
        flash("Rule updated successfully.")
        return redirect(url_for("admin_dashboard"))
    c.execute("SELECT id, ip, action, enabled FROM rules WHERE id = ?", (rule_id,))
    rule = c.fetchone()
    conn.close()
    if not rule:
        flash("Rule not found.")
        return redirect(url_for("admin_dashboard"))
    return render_template("edit_rule.html", rule=rule)


@app.route("/admin/rules/toggle/<int:rule_id>")
@admin_required
def toggle_rule(rule_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE rules SET enabled = CASE WHEN enabled = 1 THEN 0 ELSE 1 END WHERE id = ?", (rule_id,))
    conn.commit()
    conn.close()
    flash("Rule status changed.")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/rules/delete/<int:rule_id>")
@admin_required
def delete_rule(rule_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
    conn.commit()
    conn.close()
    flash("Rule deleted successfully.")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/logs")
@admin_required
def logs():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, ip, result, scanned_at FROM logs ORDER BY id DESC")
    log_data = c.fetchall()
    conn.close()
    return render_template("logs.html", logs=log_data)


@app.route("/admin/logs/clear")
@admin_required
def clear_logs():
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM logs")
    conn.commit()
    conn.close()
    flash("Logs cleared successfully.")
    return redirect(url_for("logs"))


@app.route("/user", methods=["GET", "POST"])
@user_required
def user_dashboard():
    result = None
    scanned_ip = None
    if request.method == "POST":
        scanned_ip = request.form.get("ip", "").strip()
        if not is_valid_ip(scanned_ip):
            flash("Please enter a valid IP address.")
            return redirect(url_for("user_dashboard"))
        result = scan_ip(scanned_ip)
    return render_template("user_dashboard.html", result=result, scanned_ip=scanned_ip)


@app.route("/test", methods=["GET", "POST"])
def test():
    return redirect(url_for("user_dashboard"))


@app.route("/rules")
def rules():
    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    app.run(debug=True)
