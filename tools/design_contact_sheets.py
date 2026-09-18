"""Build review sheets from existing screenshots; requires Pillow only."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


def main(output):
    for width in (360, 1440):
        for theme in ("light", "dark"):
            paths = sorted(output.glob(f"*-{width}-{theme}.png"))
            for group in range(0, len(paths), 4):
                sheet = Image.new("RGB", (1440, 1000), "#777777")
                draw = ImageDraw.Draw(sheet)
                for i, path in enumerate(paths[group : group + 4]):
                    with Image.open(path) as src:
                        top = src.crop((0, 0, src.width, min(src.height, 1200)))
                        top.thumbnail((710, 470))
                        x, y = (i % 2) * 720, (i // 2) * 500
                        draw.text((x + 8, y + 5), path.stem, fill="white")
                        sheet.paste(top, (x + 8, y + 25))
                sheet.save(output / f"sheet-{width}-{theme}-{group // 4}.jpg")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    main(parser.parse_args().directory)
