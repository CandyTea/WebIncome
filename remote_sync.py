"""Push a locally saved workbook to a deployed WebIncome site."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from local_sync import LocalWorkbookSync, RetryableSyncError, SyncRejected


def _server_error(error):
    try:
        detail = json.loads(error.read().decode("utf-8"))
        return detail.get("error") or f"服务器返回 HTTP {error.code}。"
    except Exception:
        return f"服务器返回 HTTP {error.code}。"


class RemoteUploader:
    def __init__(self, base_url, token, timeout=60):
        if not token:
            raise ValueError("缺少同步令牌。")
        self.url = base_url.rstrip("/") + "/api/sync"
        self.token = token
        self.timeout = timeout

    def upload(self, filename, contents):
        remote_name = filename if filename.lower().endswith(".xlsx") else "workbook.xlsx"
        try:
            remote_name.encode("ascii")
        except UnicodeEncodeError:
            remote_name = "workbook.xlsx"
        boundary = "----WebIncomeSync" + secrets.token_hex(16)
        body = b"".join([
            f'--{boundary}\r\nContent-Disposition: form-data; name="workbook"; filename="{remote_name}"\r\n'.encode("ascii"),
            b"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n",
            contents,
            f"\r\n--{boundary}--\r\n".encode("ascii"),
        ])
        request = urllib.request.Request(
            self.url,
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-Sync-Token": self.token,
                "User-Agent": "WebIncome-remote-sync",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            message = _server_error(error)
            if error.code in (400, 401, 403, 404):
                raise SyncRejected(message) from error
            raise RetryableSyncError(message) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise RetryableSyncError(f"无法连接服务器：{getattr(error, 'reason', error)}") from error
        except ValueError as error:
            raise RetryableSyncError("服务器返回了无法识别的内容。") from error
        if not payload.get("ok"):
            raise RetryableSyncError(payload.get("error") or "服务器未确认同步。")
        return payload


def read_config(path):
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip().lower()] = value.strip()
    return values


def main(argv=None):
    parser = argparse.ArgumentParser(description="把本地保存的 Excel 自动推送到已部署的流水查询网站。")
    parser.add_argument("--watch", type=Path, help="要监测的本地 Excel 文件")
    parser.add_argument("--url", help="网站地址，例如 http://124.221.0.127:8765")
    parser.add_argument("--token", help="服务器端设置的 WEBINCOME_SYNC_TOKEN")
    parser.add_argument("--config", type=Path, default=Path(".local/remote-sync.txt"), help="配置文件（url=、token=、watch=）")
    parser.add_argument("--once", action="store_true", help="只检查并推送一次")
    parser.add_argument("--retry-seconds", type=float, default=10, help="网络或服务器失败后的重试间隔")
    args = parser.parse_args(argv)
    config = read_config(args.config)
    watch = args.watch or (Path(config["watch"]) if config.get("watch") else None)
    url = args.url or config.get("url") or os.environ.get("WEBINCOME_SYNC_URL")
    token = args.token or config.get("token") or os.environ.get("WEBINCOME_SYNC_TOKEN")
    if not watch:
        parser.error("请用 --watch 指定要监测的 Excel 文件。")
    if not url:
        parser.error("请用 --url 或配置文件提供网站地址。")
    if not token:
        parser.error("请用 --token、配置文件或 WEBINCOME_SYNC_TOKEN 提供同步令牌。")

    uploader = RemoteUploader(url, token)

    def publish(_payload, _audit, _source, contents):
        uploader.upload(watch.name, contents)

    sync = LocalWorkbookSync(watch, publish, retry_seconds=args.retry_seconds)
    if args.once:
        sync.check_once()
        time.sleep(sync.stable_seconds + 0.1)
        sync.check_once()
        status = sync.status()
        print(json.dumps(status, ensure_ascii=False))
        return 0 if status["state"] == "synced" else 1

    print(f"监测：{watch}")
    print(f"推送到：{url}")
    sync.start()
    last = None
    try:
        while True:
            status = sync.status()
            marker = (status["state"], status["message"])
            if marker != last:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {status['message']}", flush=True)
                last = marker
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        sync.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
