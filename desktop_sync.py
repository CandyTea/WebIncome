"""Read-only workbook sync worker used by the Windows desktop assistant."""
from __future__ import annotations

import argparse
import json
import secrets
import socket
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from werkzeug.serving import ThreadedWSGIServer, WSGIRequestHandler

from app import create_app
from local_sync import LocalWorkbookSync
from remote_sync import RemoteUploader, read_config

ROOT = Path(__file__).resolve().parent


def workbook_path(value, root=ROOT):
    value = str(value).strip()
    if len(value) > 1 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1]
    if not value:
        raise ValueError("请先选择本地 Excel 文件。")
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if path.suffix.lower() != ".xlsx":
        raise ValueError("请选择 .xlsx 格式的 Excel 工作簿。")
    if not path.is_file():
        raise ValueError("找不到所选文件，请重新选择 Excel。")
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("Excel 文件不能超过 10 MB。")
    return path


def server_settings(values):
    url = values.get("url", "").strip().rstrip("/")
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("服务器网址中的端口不正确。") from error
    if parsed.scheme not in ("http", "https") or not parsed.hostname or (port is not None and port < 1):
        raise ValueError("请在服务器设置中填写完整网址，例如 https://你的网站域名。")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("请填写网站首页地址，不带账号、密码、查询条件或 # 标记。")
    token = values.get("token", "").strip()
    if not token or "\r" in token or "\n" in token:
        raise ValueError("请在服务器设置中填写有效的同步令牌。")
    return url, token


def desktop_config(mode, root=ROOT, config_path=None):
    path = config_path or root / ".local" / ("remote-sync.txt" if mode == "remote" else "local-sync.txt")
    # A BOM can be introduced by Windows Notepad. Read it without changing it.
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip().lower()] = value.strip()
    watch = values.get("watch")
    if not watch and mode == "local":
        watch = read_config(root / ".local" / "remote-sync.txt").get("watch")
    watch = watch or str(root / "全部流水表(1).xlsx")
    return workbook_path(watch, root), values


class QuietRequestHandler(WSGIRequestHandler):
    def log(self, _type, _message, *_args):
        pass


class ExclusivePreviewServer(ThreadedWSGIServer):
    # Windows SO_REUSEADDR can otherwise allow two independent local viewers
    # to bind the same port. Never share or take over another viewer's listener.
    allow_reuse_address = False
    allow_reuse_port = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class LocalPreview:
    """Own only this instance's server and watcher; never stop other servers."""

    def __init__(self, root, watch, port=8765, data_dir=None):
        local = root / ".local"
        local.mkdir(parents=True, exist_ok=True)
        password_path = local / "preview-password.txt"
        try:
            with password_path.open("x", encoding="ascii") as stream:
                stream.write(secrets.token_hex(16))
            password_path.chmod(0o600)
        except FileExistsError:
            pass
        self.app = create_app(dict(
            ADMIN_PASSWORD=password_path.read_text(encoding="ascii").strip(),
            PUBLIC_VIEW=True,
            WATCH_FILE=str(watch),
            DATA_DIR=str(data_dir or local / "server"),
            SESSION_COOKIE_SECURE=False,
        ))
        try:
            self.server = ExclusivePreviewServer("127.0.0.1", port, self.app, handler=QuietRequestHandler)
        except (OSError, SystemExit) as error:
            raise RuntimeError("本地网页端口已被占用。请先关闭原来的本地同步窗口，再点开始同步。") from error
        self.watcher = self.app.extensions["local_sync"]
        self.thread = None

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    def start(self):
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.watcher.start()

    def stop(self):
        self.watcher.stop()
        if self.thread:
            self.server.shutdown()
            self.thread.join(timeout=3)
        self.server.server_close()


def emit(state, message, console=False):
    # Structured lines keep tokens, full workbooks, and request headers out of logs.
    print(message if console else json.dumps({"state": state, "message": message}, ensure_ascii=True), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Excel 同步助手的后台进程")
    parser.add_argument("--mode", required=True, choices=("local", "remote"))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--console", action="store_true", help="输出便于阅读的控制台信息")
    args = parser.parse_args(argv)
    notify = lambda state, message: emit(state, message, args.console)
    preview = None
    watcher = None
    try:
        watch, values = desktop_config(args.mode, config_path=args.config)
        if args.mode == "remote":
            url, token = server_settings(values)
            uploader = RemoteUploader(url, token, timeout=20)
            watcher = LocalWorkbookSync(watch, lambda _payload, _audit, _source, contents: uploader.upload(watch.name, contents))
            watcher.start()
            notify("starting", "已开始监测；保存 Excel 后会自动同步到服务器。")
        else:
            preview = LocalPreview(ROOT, watch, args.port)
            preview.start()
            watcher = preview.watcher
            notify("starting", "本地网页已启动：" + preview.url)
        last = None
        while True:
            status = watcher.status()
            marker = status["state"], status["message"]
            if marker != last:
                notify(*marker)
                last = marker
            time.sleep(0.3)
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError, RuntimeError) as error:
        notify("error", str(error))
        return 1
    except Exception:
        notify("error", "同步未能启动。请检查文件路径和本地运行环境后重试，原始 Excel 没有被修改。")
        return 1
    finally:
        if preview:
            preview.stop()
        elif watcher:
            watcher.stop()


if __name__ == "__main__":
    raise SystemExit(main())
