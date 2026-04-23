"""Generate a macOS .icns app icon for Eternal Green.

Creates a green circle icon at all required sizes and packages
them into an .icns file using macOS iconutil.

Usage:
    python scripts/create_icns.py
"""

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw


SIZES = [16, 32, 64, 128, 256, 512, 1024]
OUTPUT = Path(__file__).resolve().parent.parent / "assets" / "icon.icns"


def create_icon(size: int) -> Image.Image:
    """Create a green circle icon at the given pixel size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = max(1, size // 16)
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill="#00C853",
    )
    return img


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        iconset = Path(tmpdir) / "icon.iconset"
        iconset.mkdir()

        for size in SIZES:
            # Standard resolution
            img = create_icon(size)
            img.save(iconset / f"icon_{size}x{size}.png")

            # @2x retina (half the stated size, double the pixels)
            if size <= 512:
                img2x = create_icon(size * 2)
                img2x.save(iconset / f"icon_{size}x{size}@2x.png")

        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(OUTPUT)],
            check=True,
        )

    print(f"Icon created: {OUTPUT}")


if __name__ == "__main__":
    main()
