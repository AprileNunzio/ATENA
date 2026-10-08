import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

BG = (11, 18, 32, 255)
CYAN = (41, 224, 255, 255)
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def orb(size: int = 256) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((size * 0.08, size * 0.08, size * 0.92, size * 0.92), fill=(41, 224, 255, 110))
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(size * 0.05)))
    draw = ImageDraw.Draw(image)
    ring = size * 0.16
    draw.ellipse((ring, ring, size - ring, size - ring), fill=BG, outline=CYAN, width=max(2, size // 24))
    core = size * 0.38
    draw.ellipse((core, core, size - core, size - core), fill=CYAN)
    return image


def main(target: str) -> None:
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    orb().save(path, sizes=SIZES)


if __name__ == "__main__":
    main(sys.argv[1])
