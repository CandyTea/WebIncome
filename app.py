"""Read-only driver portal with an authenticated Excel upload page."""
from __future__ import annotations

import argparse
import functools
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix

from tools.export_sheet2 import ExportError, atomic_json, extract_bytes
from local_sync import LocalWorkbookSync

ROOT = Path(__file__).resolve().parent


def create_app(config=None):
    application = Flask(__name__, static_folder=None)
    application.config.update(
        DATA_DIR=os.environ.get("WEBINCOME_DATA_DIR", str(ROOT / ".local" / "server")),
        ADMIN_PASSWORD=os.environ.get("WEBINCOME_ADMIN_PASSWORD", ""),
        VIEW_PASSWORD=os.environ.get("WEBINCOME_VIEW_PASSWORD", ""),
        PUBLIC_VIEW=os.environ.get("WEBINCOME_PUBLIC_VIEW") == "1",
        WATCH_FILE=os.environ.get("WEBINCOME_WATCH_FILE", ""),
        SYNC_TOKEN=os.environ.get("WEBINCOME_SYNC_TOKEN", ""),
        MAX_CONTENT_LENGTH=12 * 1024 * 1024,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("WEBINCOME_SECURE_COOKIE") == "1",
    )
    if config:
        application.config.update(config)
    if not application.config["ADMIN_PASSWORD"]:
        raise RuntimeError("请先设置 WEBINCOME_ADMIN_PASSWORD。")
    if not application.config["PUBLIC_VIEW"] and not application.config["VIEW_PASSWORD"]:
        application.config["VIEW_PASSWORD"] = application.config["ADMIN_PASSWORD"]
    data_dir = Path(application.config["DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    if not application.config.get("SECRET_KEY"):
        key_path = data_dir / "session.key"
        try:
            with key_path.open("x", encoding="ascii") as handle:
                handle.write(secrets.token_hex(32))
            key_path.chmod(0o600)
        except FileExistsError:
            pass
        application.config["SECRET_KEY"] = key_path.read_text(encoding="ascii").strip()
    if os.environ.get("WEBINCOME_TRUST_PROXY") == "1":
        application.wsgi_app = ProxyFix(application.wsgi_app, x_for=1, x_proto=1)
    state_path = data_dir / "current.json"

    def load_state():
        if not state_path.exists():
            return None
        return json.loads(state_path.read_text(encoding="utf-8"))

    def save_snapshot(payload, audit, source=None, contents=None):
        uploaded_at = datetime.now(timezone.utc).isoformat()
        atomic_json(state_path, {"uploadedAt": uploaded_at, "data": payload, "audit": audit, "source": source or {"kind": "upload"}})
        if source is None and watcher is not None:
            watcher.note_external_update()
        return uploaded_at

    watcher = None
    if application.config["WATCH_FILE"]:
        existing = load_state()
        existing_hash = existing["audit"]["sourceSha256"] if existing else None
        watcher = LocalWorkbookSync(application.config["WATCH_FILE"], save_snapshot, existing_hash=existing_hash)
    application.extensions["local_sync"] = watcher

    class UploadProblem(Exception):
        def __init__(self, message, status=400):
            super().__init__(message)
            self.status = status

    def parse_workbook():
        upload_file = request.files.get("workbook")
        if not upload_file or not upload_file.filename or not upload_file.filename.lower().endswith(".xlsx"):
            raise UploadProblem("请选择 .xlsx 格式的 Excel 工作簿。")
        source_bytes = upload_file.read(10 * 1024 * 1024 + 1)
        if len(source_bytes) > 10 * 1024 * 1024:
            raise UploadProblem("Excel 文件不能超过 10 MB。", 413)
        try:
            payload, audit = extract_bytes(source_bytes)
        except Exception as error:
            # Keep the last valid snapshot untouched on every import failure.
            message = str(error) if isinstance(error, ExportError) else "无法读取此 Excel，请检查文件格式，并在 Excel/WPS 中重新计算、保存后再上传。"
            raise UploadProblem(message) from error
        return payload, audit, upload_file.filename

    def csrf_token():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return session["csrf"]

    def valid_csrf():
        received = request.headers.get("X-CSRF-Token") or request.form.get("csrf", "")
        expected = session.get("csrf", "")
        return bool(received and expected and hmac.compare_digest(received, expected))

    def valid_sync_token():
        expected = application.config["SYNC_TOKEN"]
        if not expected:
            return False
        received = request.headers.get("X-Sync-Token", "")
        authorization = request.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            received = authorization[7:]
        return bool(received) and hmac.compare_digest(received.encode(), expected.encode())

    def require_user(admin=False):
        def decorate(function):
            @functools.wraps(function)
            def wrapped(*args, **kwargs):
                if not admin and application.config["PUBLIC_VIEW"]:
                    return function(*args, **kwargs)
                role = session.get("role")
                if role not in ("viewer", "admin"):
                    if request.path.startswith("/api/") or request.path.startswith("/data/"):
                        return jsonify(error="请先登录。", loginRequired=True), 401
                    return redirect("/login?next=" + ("/admin" if admin else "/"))
                if admin and role != "admin":
                    if request.path.startswith("/api/"):
                        return jsonify(error="仅管理员可以上传 Excel。"), 403
                    return render_template("access.html", csrf=csrf_token()), 403
                return function(*args, **kwargs)
            return wrapped
        return decorate

    @application.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @application.route("/login", methods=["GET", "POST"])
    def login():
        destination = request.args.get("next", "/")
        if destination not in ("/", "/admin"):
            destination = "/"
        error = None
        status = 200
        if request.method == "POST":
            password = request.form.get("password", "")
            if not valid_csrf():
                error, status = "页面已过期，请重新输入密码。", 400
            elif hmac.compare_digest(password.encode(), application.config["ADMIN_PASSWORD"].encode()):
                session.clear()
                session["role"] = "admin"
                session.permanent = True
                return redirect(destination)
            elif not application.config["PUBLIC_VIEW"] and hmac.compare_digest(password.encode(), application.config["VIEW_PASSWORD"].encode()):
                session.clear()
                session["role"] = "viewer"
                session.permanent = True
                return redirect(destination)
            else:
                error, status = "密码不正确，请重新输入。", 401
        return render_template("login.html", csrf=csrf_token(), error=error, public_view=application.config["PUBLIC_VIEW"]), status

    @application.post("/logout")
    def logout():
        if not valid_csrf():
            return "页面已过期，请刷新后重试。", 400
        session.clear()
        return redirect("/login")

    @application.get("/")
    @require_user()
    def index():
        return send_from_directory(ROOT / "dist", "index.html")

    @application.get("/data/sheet2.json")
    @require_user()
    def data():
        state = load_state()
        if state is None:
            return jsonify(error="尚未上传 Excel，请管理员先上传工作簿。", empty=True), 404
        response = jsonify(state["data"])
        response.headers["X-Data-Version"] = state["uploadedAt"]
        return response

    @application.get("/api/data-status")
    @require_user()
    def data_status():
        state = load_state()
        return jsonify(version=state["uploadedAt"] if state else None)

    @application.get("/api/local-sync")
    @require_user(admin=True)
    def local_sync():
        state = load_state()
        return jsonify(sync=watcher.status() if watcher else {"enabled": False},
                       version=state["uploadedAt"] if state else None,
                       audit=state["audit"] if state else None)

    @application.get("/admin")
    @require_user(admin=True)
    def admin():
        state = load_state()
        return render_template("admin.html", csrf=csrf_token(), audit=state["audit"] if state else None, uploaded_at=state["uploadedAt"] if state else None, local_sync=watcher.status() if watcher else None)

    @application.post("/api/upload")
    @require_user(admin=True)
    def upload():
        if not valid_csrf():
            return jsonify(error="页面已过期，请刷新后重新上传。"), 400
        try:
            payload, audit, _filename = parse_workbook()
        except UploadProblem as error:
            return jsonify(error=str(error)), error.status
        try:
            uploaded_at = save_snapshot(payload, audit)
        except OSError:
            application.logger.exception("Cannot save imported data")
            return jsonify(error="服务器未能保存数据，原有数据已保留。请检查服务器存储权限。"), 500
        return jsonify(ok=True, audit=audit, uploadedAt=uploaded_at)

    @application.post("/api/sync")
    def sync_upload():
        if not application.config["SYNC_TOKEN"]:
            return jsonify(error="未启用同步接口。"), 404
        if not valid_sync_token():
            return jsonify(error="同步令牌不正确。"), 401
        try:
            payload, audit, filename = parse_workbook()
        except UploadProblem as error:
            return jsonify(error=str(error)), error.status
        try:
            uploaded_at = save_snapshot(payload, audit, {"kind": "remote-sync", "fileName": filename})
        except OSError:
            application.logger.exception("Cannot save synced data")
            return jsonify(error="服务器未能保存数据，原有数据已保留。请检查服务器存储权限。"), 500
        return jsonify(ok=True, audit=audit, uploadedAt=uploaded_at)

    @application.errorhandler(RequestEntityTooLarge)
    def too_large(_error):
        return jsonify(error="文件过大，请上传不超过 10 MB 的 Excel。"), 413

    @application.get("/<path:asset>")
    def assets(asset):
        if asset not in ("styles.css", "app.mjs", "query.mjs", "icon.svg", "admin.mjs", "portal.css"):
            return "Not found", 404
        return send_from_directory(ROOT / "dist", asset)

    return application


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--watch", type=Path, help="本地自动同步的 Excel 文件")
    args = parser.parse_args()
    application = create_app({"WATCH_FILE": str(args.watch.resolve())} if args.watch else None)
    local_sync = application.extensions["local_sync"]
    if local_sync:
        local_sync.start()
    try:
        application.run(host="127.0.0.1", port=args.port, debug=False)
    finally:
        if local_sync:
            local_sync.stop()
