"""Programmatic image fixture builder for Phase 3 tests."""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FIXTURES_ROOT = Path(__file__).resolve().parent
VALID_ROOT = FIXTURES_ROOT / "valid" / "image"
BROKEN_ROOT = FIXTURES_ROOT / "broken" / "image"

FONT_CANDIDATES = [
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/STHeiti Medium.ttc"),
    Path("/System/Library/Fonts/STHeiti Light.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
]


def ensure_dirs() -> None:
    for path in (VALID_ROOT, BROKEN_ROOT):
        path.mkdir(parents=True, exist_ok=True)


def build_all() -> None:
    ensure_dirs()
    build_valid()
    build_broken()


def build_valid() -> None:
    _build_text_image(
        VALID_ROOT / "atlas-dependency.png",
        [
            "Atlas 依賴 Mobile Gateway",
            "Owner Iris",
            "Status 正常",
        ],
        fmt="PNG",
    )
    _build_text_image(
        VALID_ROOT / "zh-ops.png",
        [
            "供應商延遲 3 天",
            "採購重排完成",
            "風險下降",
        ],
        fmt="PNG",
    )
    _build_text_image(
        VALID_ROOT / "mixed-status.jpg",
        [
            "Borealis affects Billing Service",
            "ETA 3 days",
            "Owner Mia",
        ],
        fmt="JPEG",
    )
    _build_rotated_notice(VALID_ROOT / "rotated-notice.png")
    _build_multi_column(VALID_ROOT / "multi-column.jpeg")
    _build_no_text(VALID_ROOT / "no-text.png")


def build_broken() -> None:
    atlas_png = VALID_ROOT / "atlas-dependency.png"
    corrupt = BROKEN_ROOT / "corrupt.png"
    corrupt.write_bytes(atlas_png.read_bytes()[:96])

    timeout = BROKEN_ROOT / "timeout.png"
    shutil.copy2(atlas_png, timeout)

    empty = BROKEN_ROOT / "empty.jpg"
    empty.write_bytes(b"")

    oversized = BROKEN_ROOT / "oversized.jpg"
    shutil.copy2(VALID_ROOT / "mixed-status.jpg", oversized)
    with oversized.open("ab") as handle:
        handle.write(b"\x00" * (2 * 1024 * 1024))


def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    raise RuntimeError("No CJK-capable font found for image fixture generation")


def _build_text_image(path: Path, lines: list[str], *, fmt: str) -> None:
    image = Image.new("RGB", (1800, 960), "white")
    draw = ImageDraw.Draw(image)
    title_font = _font(68)
    body_font = _font(58)
    draw.rectangle((60, 60, 1740, 900), outline="#d9d9d9", width=4)
    y = 150
    for index, line in enumerate(lines):
        font = title_font if index == 0 else body_font
        draw.text((120, y), line, fill="#111111", font=font)
        y += 150
    if fmt == "JPEG":
        image.save(path, format=fmt, quality=95)
    else:
        image.save(path, format=fmt)


def _build_rotated_notice(path: Path) -> None:
    base = Image.new("RGB", (1800, 960), "#f5f5f5")
    draw = ImageDraw.Draw(base)
    font = _font(62)
    lines = [
        "Atlas 會影響 Billing Service",
        "Friday rollout",
        "Risk low",
    ]
    y = 180
    for line in lines:
        draw.text((160, y), line, fill="#5a5a5a", font=font)
        y += 150
    rotated = base.rotate(2.2, resample=Image.Resampling.BICUBIC, expand=False, fillcolor="#f5f5f5")
    rotated.save(path, format="PNG")


def _build_multi_column(path: Path) -> None:
    image = Image.new("RGB", (2200, 1200), "white")
    draw = ImageDraw.Draw(image)
    font = _font(54)
    left = ["Owner Mia", "Budget 135", "Search green"]
    right = ["Fallback supplier", "ETA Friday", "QA ready"]
    y = 160
    for line in left:
        draw.text((140, y), line, fill="#151515", font=font)
        y += 170
    y = 160
    for line in right:
        draw.text((1180, y), line, fill="#151515", font=font)
        y += 170
    image.save(path, format="JPEG", quality=95)


def _build_no_text(path: Path) -> None:
    image = Image.new("RGB", (1400, 900), "#f4f7fb")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((120, 140, 620, 420), radius=32, fill="#2b6cb0")
    draw.rounded_rectangle((760, 140, 1260, 420), radius=32, fill="#38a169")
    draw.ellipse((280, 520, 560, 800), fill="#ecc94b")
    draw.ellipse((840, 520, 1120, 800), fill="#ed8936")
    image.save(path, format="PNG")


if __name__ == "__main__":
    build_all()
