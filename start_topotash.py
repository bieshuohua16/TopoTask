#!/usr/bin/env python
"""TopoTash 拓事 · 本地启动器。

桌面快捷方式调用的就是这个脚本：检查环境 → 确认数据库 → 启动 Flask →
自动打开浏览器。重复双击不会启动第二个实例，只会把页面重新打开。

用法：
    python start_topotash.py             # 启动并打开浏览器
    python start_topotash.py --port 5050 # 换一个端口
    python start_topotash.py --debug     # 打开 Flask 调试模式
    python start_topotash.py --no-browser
    python start_topotash.py --db D:\\data\\topotash.db
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import socket
import sqlite3
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
DEFAULT_PORT = 5000
STARTUP_TIMEOUT = 30.0

# 本机健康检查不应经过系统代理。
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _set_console_title() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.kernel32.SetConsoleTitleW("TopoTash 拓事 · 本地服务")
    except Exception:
        pass


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection((HOST, port), timeout=0.8):
            return True
    except OSError:
        return False


def _health_ok(port: int) -> bool:
    url = f"http://{HOST}:{port}/healthz"
    try:
        with _OPENER.open(url, timeout=2.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload.get("ok") is True
    except Exception:
        return False


def _wait_health(port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _health_ok(port):
            return True
        time.sleep(0.2)
    return False


def _open_browser_when_ready(port: int, url: str) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if _health_ok(port):
            try:
                opened = webbrowser.open(url)
            except Exception:
                opened = False
            if opened:
                print(f"       [OK] 浏览器已打开 {url}", flush=True)
            else:
                print(f"       [!!] 无法自动打开浏览器，请手动访问 {url}", flush=True)
            return
        time.sleep(0.4)
    print(f"       [!!] 等待服务就绪超时，请手动访问 {url}", flush=True)


def _project_count(flask_app) -> int | None:
    try:
        conn = sqlite3.connect(flask_app.config["DATABASE"])
        try:
            return conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        finally:
            conn.close()
    except Exception:
        return None


def _fail(message: str) -> int:
    print(f"\n[错误] {message}", flush=True)
    if sys.stdin and sys.stdin.isatty():
        try:
            input("\n按回车键退出 ...")
        except (EOFError, KeyboardInterrupt):
            pass
    return 1


def _banner(port: int, debug: bool) -> None:
    print("=" * 56)
    print("  TopoTash 拓事 · 项目工作台")
    print(f"  地址  http://{HOST}:{port}")
    if debug:
        print("  模式  调试（debug）")
    print("=" * 56, flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="启动 TopoTash 本地服务")
    parser.add_argument("--port", type=int, help=f"监听端口（默认 {DEFAULT_PORT}）")
    parser.add_argument("--db", help="数据库文件路径")
    parser.add_argument("--debug", action="store_true", help="启用 Flask 调试模式")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args(argv)
    if args.db:
        os.environ["TOPOTASH_DB"] = str(Path(args.db).expanduser().resolve())

    port = args.port or int(os.environ.get("TOPOTASH_PORT", DEFAULT_PORT))
    debug = args.debug or os.environ.get("TOPOTASH_DEBUG", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not 1 <= port <= 65535:
        return _fail(f"端口号不合法：{port}")

    url = f"http://{HOST}:{port}"
    _set_console_title()
    _banner(port, debug)

    requirements = ROOT / "requirements.txt"
    try:
        import flask  # noqa: F401
    except Exception:
        return _fail(
            "未找到 Flask，无法启动。\n"
            "       请先双击项目目录里的「首次启动.bat」，或执行：\n"
            f'       "{sys.executable}" -m pip install -r "{requirements}"'
        )

    # 已有一个实例在运行：只打开浏览器，不重复启动。
    if _port_open(port):
        if args.db:
            try:
                with _OPENER.open(f"{url}/healthz", timeout=2.0) as response:
                    running = json.loads(response.read().decode("utf-8"))
                expected = os.path.normcase(os.environ["TOPOTASH_DB"])
                actual = os.path.normcase(str(Path(running.get("database", "")).resolve()))
                if actual != expected:
                    return _fail("该端口的实例使用其他数据库，请用 --port 指定另一个端口。")
            except (OSError, ValueError):
                return _fail(f"无法确认端口 {port} 上实例的数据库，请换一个端口启动。")
        if _wait_health(port, 4.0):
            print(f"\n       TopoTash 已经在运行：{url}", flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            return 0
        return _fail(
            f"端口 {port} 已被其他程序占用。\n"
            "       请关闭占用该端口的程序，或换一个端口启动：\n"
            "       python start_topotash.py --port 5050"
        )

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        from app import app as flask_app  # noqa: WPS433
    except Exception:
        print()
        import traceback

        traceback.print_exc()
        return _fail(
            "应用加载失败，数据库或代码可能有问题。\n"
            "       可先运行 python setup_first_run.py 检查环境。"
        )

    count = _project_count(flask_app)
    if count == 0:
        print(
            "\n       提示：数据库里还没有项目。"
            "可运行「首次启动.bat」写入示例数据，"
            "或直接在页面里新建项目。",
            flush=True,
        )
    elif count is not None:
        print(f"\n       当前共有 {count} 个项目。", flush=True)

    print("\n       正在启动本地服务 ...", flush=True)
    print("       关闭窗口或按 Ctrl+C 即可停止。\n", flush=True)

    if not args.no_browser:
        threading.Thread(
            target=_open_browser_when_ready,
            args=(port, url),
            daemon=True,
        ).start()

    try:
        flask_app.run(
            host=HOST,
            port=port,
            debug=debug,
            use_reloader=False,
            threaded=True,
        )
    except KeyboardInterrupt:
        pass
    except OSError as exc:
        # 极小概率的竞态：另一个窗口刚好抢先启动，此时直接复用。
        if _wait_health(port, 3.0):
            print(f"\n       TopoTash 已经在运行：{url}", flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            return 0
        return _fail(f"启动失败：{exc}")
    finally:
        print("\n       TopoTash 已停止。", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
