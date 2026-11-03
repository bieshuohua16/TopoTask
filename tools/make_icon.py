"""Generate the TopoTash Windows icon (``static/topotash.ico``).

The project's ``static/favicon.svg`` is redrawn here as a scalable raster:
rounded square with an indigo → cyan gradient and a white network glyph.
Only the standard library is used, so no Pillow is required.

Usage:
    python tools/make_icon.py                 # write static/topotash.ico
    python tools/make_icon.py --preview p.png # also write a 256px PNG preview
"""
from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ICON = ROOT / "static" / "topotash.ico"

# Palette and geometry mirror static/favicon.svg (viewBox 0 0 32 32).
COLOR_FROM = (99, 102, 241)   # #6366f1
COLOR_TO = (34, 211, 238)     # #22d3ee
WHITE = (255, 255, 255)

VIEW = 32.0
CORNER_RADIUS = 8.0
STROKE_HALF = 1.0             # stroke-width: 2

CIRCLES = ((10.0, 10.0, 3.2), (23.0, 9.0, 3.2), (16.0, 23.0, 3.2))
CAPSULES = ((13.0, 11.2, 14.8, 20.0), (19.8, 11.0, 17.4, 20.0), (13.0, 9.0, 19.5, 9.0))

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


# --------------------------------------------------------------- shape tests
def _in_rounded_rect(x: float, y: float, size: float, radius: float) -> bool:
    if x < 0.0 or y < 0.0 or x > size or y > size:
        return False
    cx = min(max(x, radius), size - radius)
    cy = min(max(y, radius), size - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius


def _in_ring(x: float, y: float, cx: float, cy: float, radius: float) -> bool:
    dist2 = (x - cx) ** 2 + (y - cy) ** 2
    inner = radius - STROKE_HALF
    outer = radius + STROKE_HALF
    return inner * inner <= dist2 <= outer * outer


def _in_capsule(x: float, y: float, x1: float, y1: float, x2: float, y2: float) -> bool:
    dx, dy = x2 - x1, y2 - y1
    length2 = dx * dx + dy * dy
    if length2 == 0.0:
        t = 0.0
    else:
        t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length2))
    px, py = x1 + t * dx, y1 + t * dy
    return (x - px) ** 2 + (y - py) ** 2 <= STROKE_HALF * STROKE_HALF


def _in_glyph(x: float, y: float) -> bool:
    for cx, cy, radius in CIRCLES:
        if _in_ring(x, y, cx, cy, radius):
            return True
    for x1, y1, x2, y2 in CAPSULES:
        if _in_capsule(x, y, x1, y1, x2, y2):
            return True
    return False


def _gradient(x: float, y: float) -> tuple[float, float, float]:
    t = max(0.0, min(1.0, (x + y) / (2.0 * VIEW)))
    return tuple(a + (b - a) * t for a, b in zip(COLOR_FROM, COLOR_TO))


def _samples_for(size: int) -> int:
    if size <= 32:
        return 6
    if size <= 64:
        return 4
    return 2


# ------------------------------------------------------------------ raster
def render_rgba(size: int) -> bytes:
    """Render one icon size as RGBA bytes (row-major, top-down)."""
    scale = size / VIEW
    samples = _samples_for(size)
    total = samples * samples
    out = bytearray(size * size * 4)
    for py in range(size):
        for px in range(size):
            r = g = b = 0.0
            covered = 0
            for sy in range(samples):
                for sx in range(samples):
                    x = (px + (sx + 0.5) / samples) / scale
                    y = (py + (sy + 0.5) / samples) / scale
                    if not _in_rounded_rect(x, y, VIEW, CORNER_RADIUS):
                        continue
                    covered += 1
                    if _in_glyph(x, y):
                        cr, cg, cb = WHITE
                    else:
                        cr, cg, cb = _gradient(x, y)
                    r += cr
                    g += cg
                    b += cb
            offset = (py * size + px) * 4
            if covered:
                out[offset] = int(round(r / covered))
                out[offset + 1] = int(round(g / covered))
                out[offset + 2] = int(round(b / covered))
                out[offset + 3] = int(round(255 * covered / total))
    return bytes(out)


# ----------------------------------------------------------------- encoding
def _png_bytes(rgba: bytes, width: int, height: int) -> bytes:
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)  # filter: none
        raw += rgba[y * stride:(y + 1) * stride]

    def chunk(tag: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(tag + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", checksum)

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(raw), 9)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def _bmp_entry(rgba: bytes, width: int, height: int) -> bytes:
    """32-bit BGRA DIB plus the (unused) AND mask, as stored in .ico files."""
    mask_stride = ((width + 31) // 32) * 4
    image_size = width * height * 4 + mask_stride * height
    header = struct.pack(
        "<IiiHHIIiiII",
        40, width, height * 2, 1, 32, 0, image_size, 0, 0, 0, 0,
    )
    rows = bytearray()
    stride = width * 4
    for y in range(height - 1, -1, -1):
        row = rgba[y * stride:(y + 1) * stride]
        for x in range(width):
            r, g, b, a = row[x * 4:x * 4 + 4]
            rows += bytes((b, g, r, a))
    rows += b"\x00" * (mask_stride * height)
    return header + bytes(rows)


def encode_ico(sizes: tuple[int, ...] = ICON_SIZES) -> bytes:
    """Encode the multi-resolution icon (no filesystem access)."""
    images: list[tuple[int, bytes]] = []
    for size in sizes:
        rgba = render_rgba(size)
        # 256px is stored as PNG (Vista+) to keep the file small.
        payload = _png_bytes(rgba, size, size) if size >= 256 else _bmp_entry(rgba, size, size)
        images.append((size, payload))

    offset = 6 + 16 * len(images)
    directory = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    for size, payload in images:
        dimension = 0 if size >= 256 else size
        directory += struct.pack(
            "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(payload), offset
        )
        offset += len(payload)

    return bytes(directory) + b"".join(payload for _, payload in images)


def build_icon(path: Path, sizes: tuple[int, ...] = ICON_SIZES) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_ico(sizes))
    return path


def ensure_icon(path: Path = DEFAULT_ICON, force: bool = False) -> Path:
    """Create the icon when missing/outdated; never fatal for the caller."""
    try:
        if not force and path.is_file() and path.stat().st_mtime >= Path(__file__).stat().st_mtime:
            return path
        return build_icon(path)
    except OSError as exc:  # read-only checkout, locked file, ...
        raise RuntimeError(f"无法写入图标 {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 TopoTash 的 Windows 图标")
    parser.add_argument("output", nargs="?", default=str(DEFAULT_ICON), help="输出 .ico 路径")
    parser.add_argument("--preview", help="额外输出一张 256px PNG 预览图")
    parser.add_argument("--force", action="store_true", help="即使已存在也重新生成")
    args = parser.parse_args(argv)

    target = Path(args.output)
    build_icon(target)
    print(f"icon written: {target} ({target.stat().st_size} bytes)")
    if args.preview:
        preview = Path(args.preview)
        preview.parent.mkdir(parents=True, exist_ok=True)
        preview.write_bytes(_png_bytes(render_rgba(256), 256, 256))
        print(f"preview written: {preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
