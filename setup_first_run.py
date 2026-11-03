#!/usr/bin/env python
"""TopoTash 拓事 · 首次启动向导。

推荐双击同目录的「首次启动.bat」，它会自动找到 Python 并运行本脚本。

本脚本依次完成：
    1. 检查 Python 版本与 Flask 依赖（缺少时自动 pip 安装）
    2. 初始化 SQLite 数据库（幂等，可安全重复运行）
    3. 数据库为空时写入示例项目 / 任务 / 拓扑图
    4. 在桌面创建启动快捷方式，之后双击即可启动

可选参数：
    --db PATH            指定数据库文件（默认 ./topotash.db）
    --desktop-dir PATH   指定快捷方式目录（默认当前用户桌面）
    --icon PATH          指定图标输出路径（默认 ./static/topotash.ico）
    --skip-seed          不写入示例数据
    --no-shortcut        不创建桌面快捷方式
    --force-icon         强制重新生成图标
"""
from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import sqlite3
import subprocess
import sys
import traceback
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MIN_PYTHON = (3, 10)
FLASK_MAJOR = 3
CORE_TABLES = ("projects", "tasks", "task_categories", "diagrams", "diagram_nodes", "app_settings")
SHORTCUT_NAME = "TopoTash 拓事.lnk"
SHORTCUT_DESC = "TopoTash 拓事 · 项目工作台（本地服务）"
DEFAULT_PORT = 5000
TOTAL_STEPS = 5

SHORTCUT_PS = (
    "$ErrorActionPreference='Stop';"
    "$shell=New-Object -ComObject WScript.Shell;"
    "$link=$shell.CreateShortcut($env:TOPOTASH_LNK);"
    "$link.TargetPath=$env:TOPOTASH_TARGET;"
    "$link.Arguments=$env:TOPOTASH_ARGS;"
    "$link.WorkingDirectory=$env:TOPOTASH_WORKDIR;"
    "$link.IconLocation=$env:TOPOTASH_ICON;"
    "$link.Description=$env:TOPOTASH_DESC;"
    "$link.WindowStyle=1;"
    "$link.Save()"
)


class SetupError(Exception):
    """可预期的配置 / 环境错误，直接展示给用户。"""


# ------------------------------------------------------------------ 输出
def heading(step: int, text: str) -> None:
    print(f"\n[{step}/{TOTAL_STEPS}] {text}", flush=True)


def info(text: str) -> None:
    print(f"       {text}", flush=True)


def ok(text: str = "完成") -> None:
    print(f"       [OK] {text}", flush=True)


def warn(text: str) -> None:
    print(f"       [!!] {text}", flush=True)


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace").strip()


def human_size(num: int) -> str:
    size = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{num} B"


# -------------------------------------------------------------- 1. Python
def step_python() -> None:
    heading(1, "检查 Python 环境")
    bits = 64 if sys.maxsize > 2**32 else 32
    info(f"版本    Python {sys.version.split()[0]}（{bits} 位，{sys.platform}）")
    info(f"解释器  {sys.executable}")

    if sys.version_info < MIN_PYTHON:
        raise SetupError(
            f"Python 版本过低：需要 {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 或更高，"
            f"当前为 {sys.version.split()[0]}。\n"
            "       请从 https://www.python.org/downloads/ 安装新版后重新运行。"
        )
    if not (ROOT / "app.py").is_file():
        raise SetupError(f"项目文件不完整：{ROOT / 'app.py'} 不存在。")
    if not (ROOT / "start_topotash.py").is_file():
        raise SetupError(f"项目文件不完整：{ROOT / 'start_topotash.py'} 不存在。")
    ok()


# ------------------------------------------------------------ 2. 依赖
def _flask_version() -> str | None:
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("flask")
    except PackageNotFoundError:
        return None


def _flask_compatible(version: str) -> bool:
    try:
        major = int(version.split(".")[0])
    except (ValueError, IndexError):
        return False
    return major == FLASK_MAJOR


def _verify_flask() -> None:
    try:
        import flask  # noqa: F401
    except Exception as exc:  # pragma: no cover - depends on local install
        raise SetupError(f"Flask 已安装但无法导入：{exc}") from exc


def step_dependencies() -> None:
    heading(2, "检查依赖")
    version = _flask_version()
    if version and _flask_compatible(version):
        info(f"Flask {version} 已安装")
        _verify_flask()
        ok()
        return

    if version:
        info(f"Flask {version} 版本不满足要求（需要 3.x），尝试升级 ...")
    else:
        info("未检测到 Flask，开始安装依赖 ...")

    pip_check = subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if pip_check.returncode != 0:
        raise SetupError(
            "当前 Python 没有可用的 pip，无法自动安装依赖。\n"
            "       请重新安装 Python（安装时勾选 pip），或手动执行：\n"
            f'       "{sys.executable}" -m ensurepip --upgrade'
        )

    requirements = ROOT / "requirements.txt"
    if not requirements.is_file():
        raise SetupError(f"缺少依赖清单：{requirements}")

    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "-r",
        str(requirements),
        "--disable-pip-version-check",
    ]
    info("执行：" + subprocess.list2cmdline(cmd))
    result = subprocess.call(cmd)
    if result != 0:
        raise SetupError(
            "依赖安装失败（pip 退出码 "
            f"{result}）。请检查网络后重试，或手动执行：\n"
            f'       "{sys.executable}" -m pip install -r "{requirements}"\n'
            "       国内网络可加镜像："
            " -i https://pypi.tuna.tsinghua.edu.cn/simple"
        )

    version = _flask_version()
    if not version or not _flask_compatible(version):
        raise SetupError(
            "安装后仍未检测到 Flask 3.x，请确认上面的 pip 输出。\n"
            f'       可尝试："{sys.executable}" -m pip install -r "{requirements}"'
        )
    info(f"Flask {version} 安装完成")
    _verify_flask()
    ok()


# ---------------------------------------------------------- 3. 数据库
def inspect_db(path: Path) -> dict:
    if not path.is_file():
        raise SetupError(f"数据库文件不存在：{path}")
    conn = sqlite3.connect(path)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        missing = [name for name in CORE_TABLES if name not in tables]
        if missing:
            raise SetupError(f"数据库表结构不完整，缺少：{', '.join(missing)}")
        counts = {
            name: conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in ("projects", "tasks", "diagrams")
        }
    finally:
        conn.close()
    counts["tables"] = len(tables)
    counts["size"] = path.stat().st_size
    return counts


def step_database(db_path: Path) -> tuple:
    heading(3, "初始化数据库")
    db_path = db_path.resolve()
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SetupError(f"无法创建数据库目录 {db_path.parent}：{exc}") from exc

    info(f"数据库  {db_path}")
    os.environ["TOPOTASH_DB"] = str(db_path)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    try:
        import app as app_module
        from db import init_db

        init_db(app_module.app)
    except SetupError:
        raise
    except Exception as exc:
        raise SetupError(
            f"初始化数据库失败：{exc}\n"
            f"       请确认 {db_path} 没有被其他程序占用，“属性 → 只读”未勾选，"
            "且当前用户有写入权限。"
        ) from exc

    stats = inspect_db(Path(app_module.app.config["DATABASE"]))
    info(f"表结构  {stats['tables']} 张表，文件 {human_size(stats['size'])}")
    info(
        "现有数据  "
        f"{stats['projects']} 个项目 / {stats['tasks']} 个任务 / {stats['diagrams']} 张拓扑图"
    )
    ok()
    return app_module, stats


# ---------------------------------------------------------- 4. 示例数据
def step_seed(app_module, stats: dict, skip: bool) -> dict:
    heading(4, "写入示例数据")
    if skip:
        info("已按参数跳过（--skip-seed）")
        return stats
    if stats["projects"] > 0:
        info(f"数据库已有 {stats['projects']} 个项目，保留现有数据，不会重复写入")
        return stats

    info("数据库为空，正在写入示例项目、任务与拓扑图 ...")
    try:
        from tools.seed_demo import seed_demo

        with app_module.app.app_context():
            created = seed_demo()
    except Exception as exc:
        raise SetupError(
            "写入示例数据失败（事务已回滚，数据库未被改坏）："
            f"{exc}\n"
            '       可稍后手动执行：python app.py seed-demo'
        ) from exc

    stats = inspect_db(Path(app_module.app.config["DATABASE"]))
    info(f"新增 {created} 个示例项目")
    info(
        "当前数据  "
        f"{stats['projects']} 个项目 / {stats['tasks']} 个任务 / {stats['diagrams']} 张拓扑图"
    )
    ok()
    return stats


# ---------------------------------------------------------- 5. 快捷方式
def _known_folder_desktop() -> Path | None:
    """通过 Windows Known Folder API 获取桌面（兼容 OneDrive 重定向）。"""
    if os.name != "nt":
        return None
    try:
        from ctypes import POINTER, Structure, byref, c_ubyte, c_void_p, c_wchar_p

        class GUID(Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", c_ubyte * 8),
            ]

        # FOLDERID_Desktop = {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
        folder_id = GUID(
            0xB4BFCC3A,
            0xDB2C,
            0x424C,
            (c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41),
        )
        result = c_wchar_p()
        get_path = ctypes.windll.shell32.SHGetKnownFolderPath
        get_path.argtypes = [
            POINTER(GUID),
            wintypes.DWORD,
            wintypes.HANDLE,
            POINTER(c_wchar_p),
        ]
        get_path.restype = ctypes.c_long
        if get_path(byref(folder_id), 0, None, byref(result)) != 0 or not result.value:
            return None
        value = result.value
        ctypes.windll.ole32.CoTaskMemFree(ctypes.cast(result, c_void_p))
        return Path(value)
    except Exception:
        return None


def default_desktop() -> Path:
    if os.name == "nt":
        desktop = _known_folder_desktop()
        if desktop:
            return desktop
        profile = os.environ.get("USERPROFILE")
        if profile:
            candidate = Path(profile) / "Desktop"
            if candidate.is_dir():
                return candidate
    return Path.home() / "Desktop"


def _powershell() -> str:
    for name in ("powershell.exe", "powershell"):
        found = shutil.which(name)
        if found:
            return found
    fallback = Path(os.environ.get("SystemRoot", r"C:\Windows")) / (
        r"System32\WindowsPowerShell\v1.0\powershell.exe"
    )
    if fallback.is_file():
        return str(fallback)
    raise SetupError("找不到 Windows PowerShell，无法自动创建快捷方式。")


def create_shortcut(
    link: Path,
    target: str,
    arguments: str,
    workdir: Path,
    icon: Path | None,
) -> None:
    if os.name != "nt":
        raise SetupError("桌面快捷方式目前只支持 Windows。")

    env = os.environ.copy()
    env.update(
        {
            "TOPOTASH_LNK": str(link),
            "TOPOTASH_TARGET": target,
            "TOPOTASH_ARGS": arguments,
            "TOPOTASH_WORKDIR": str(workdir),
            "TOPOTASH_ICON": f"{icon},0" if icon else f"{target},0",
            "TOPOTASH_DESC": SHORTCUT_DESC,
        }
    )
    cmd = [
        _powershell(),
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        SHORTCUT_PS,
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            timeout=90,
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired as exc:
        raise SetupError("创建快捷方式超时（PowerShell 无响应）。") from exc
    except OSError as exc:
        raise SetupError(f"无法启动 PowerShell：{exc}") from exc

    if proc.returncode != 0:
        detail = _decode(proc.stderr) or _decode(proc.stdout)
        raise SetupError(
            "创建快捷方式失败"
            + (f"：{detail}" if detail else f"（PowerShell 退出码 {proc.returncode}）")
            + "\n       可稍后重新运行本脚本，或手动右键 start_topotash.py 创建快捷方式。"
        )


def step_shortcut(args) -> Path | None:
    heading(5, "创建桌面快捷方式")
    launcher = ROOT / "start_topotash.py"

    icon: Path | None
    if args.icon:
        icon = Path(args.icon).expanduser().resolve()
    else:
        icon = ROOT / "static" / "topotash.ico"
    try:
        from tools.make_icon import ensure_icon

        ensure_icon(icon, force=args.force_icon)
        info(f"图标    {icon}")
    except Exception as exc:
        warn(f"图标生成失败，将使用 Python 默认图标：{exc}")
        icon = None

    desktop = (
        Path(args.desktop_dir).expanduser().resolve()
        if args.desktop_dir
        else default_desktop()
    )
    if not desktop.is_dir():
        raise SetupError(
            f"桌面目录不存在：{desktop}\n"
            "       可用 --desktop-dir 指定其他目录，或检查桌面是否被重定向。"
        )
    info(f"桌面    {desktop}")

    link = desktop / SHORTCUT_NAME
    create_shortcut(
        link,
        target=sys.executable,
        arguments=f'"{launcher}"',
        workdir=ROOT,
        icon=icon,
    )
    if not link.is_file():
        raise SetupError(f"快捷方式创建后未找到文件：{link}")
    ok(f"已创建 {link.name}")
    return link


# ------------------------------------------------------------------ 汇总
def summary(db_path: Path, stats: dict, link: Path | None) -> None:
    print("\n" + "-" * 64)
    print(" 全部完成，TopoTash 已经可以使用。")
    print(f"   数据库    {db_path}")
    if link:
        print(f"   快捷方式  {link}")
    print(f"   访问地址  http://127.0.0.1:{DEFAULT_PORT}")
    print()
    if link:
        print(" 以后启动：双击桌面上的「TopoTash 拓事」")
    else:
        print(" 启动方式：python start_topotash.py")
    print(" 停止服务：在服务窗口按 Ctrl+C，或直接关闭该窗口。")
    print("-" * 64)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TopoTash 首次启动向导")
    parser.add_argument("--db", help="数据库文件路径（默认 ./topotash.db）")
    parser.add_argument("--desktop-dir", help="快捷方式输出目录（默认当前用户桌面）")
    parser.add_argument("--icon", help="图标输出路径（默认 ./static/topotash.ico）")
    parser.add_argument("--skip-seed", action="store_true", help="不写入示例数据")
    parser.add_argument("--no-shortcut", action="store_true", help="不创建桌面快捷方式")
    parser.add_argument("--force-icon", action="store_true", help="强制重新生成图标")
    args = parser.parse_args(argv)

    print("=" * 64)
    print(" TopoTash 拓事 · 首次启动向导")
    print(f" 项目目录  {ROOT}")
    print("=" * 64)

    db_path = Path(args.db).expanduser() if args.db else ROOT / "topotash.db"
    link: Path | None = None
    try:
        step_python()
        step_dependencies()
        app_module, stats = step_database(db_path)
        stats = step_seed(app_module, stats, args.skip_seed)
        if args.no_shortcut:
            heading(5, "创建桌面快捷方式")
            info("已按参数跳过（--no-shortcut）")
        else:
            link = step_shortcut(args)
        summary(Path(app_module.app.config["DATABASE"]), stats, link)
        return 0
    except SetupError as exc:
        print(f"\n[失败] {exc}", flush=True)
        print(
            "\n排查建议：\n"
            "  · 按上面的提示处理后可重新运行本脚本，不会重复写入示例数据；\n"
            "  · 在本目录运行 python setup_first_run.py --help 查看全部参数；\n"
            "  · 如果卡在依赖安装，确认网络可访问 PyPI（可给 pip 加国内镜像）。"
        )
        return 1
    except KeyboardInterrupt:
        print("\n[取消] 已中止，可能有步骤未完成；重新运行本脚本即可继续。")
        return 130
    except Exception:
        traceback.print_exc()
        print("\n[失败] 出现未预期的错误，详见上面的堆栈。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
