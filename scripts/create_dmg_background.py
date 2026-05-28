from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "dmg-background.png"
WIDTH = 720
HEIGHT = 440


def font(size, bold=False):
    candidates = [
        "/System/Library/Fonts/STHeiti Medium.ttc" if bold else "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/SFNS.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def text_center(draw, xy, text, font_obj, fill):
    box = draw.textbbox((0, 0), text, font=font_obj)
    x = xy[0] - (box[2] - box[0]) / 2
    y = xy[1] - (box[3] - box[1]) / 2
    draw.text((x, y), text, font=font_obj, fill=fill)


def make_background():
    img = Image.new("RGB", (WIDTH, HEIGHT), "#ffffff")
    draw = ImageDraw.Draw(img)

    title_font = font(38)
    mac_font = font(13)
    arrow_font = font(30)
    note_font = font(15)
    version_font = font(14)

    text_center(draw, (WIDTH / 2, 88), "定格截图", title_font, "#5b5b5f")
    text_center(draw, (WIDTH / 2, 124), "for Mac", mac_font, "#6b6b70")
    text_center(draw, (WIDTH / 2, 236), "→", arrow_font, "#2f2f33")
    text_center(draw, (WIDTH / 2, 332), "拖动“定格截图”到文件夹，即可安装", note_font, "#c3c6cc")
    text_center(draw, (WIDTH / 2, 360), "安装后可在「应用程序」或 Launchpad 中打开", version_font, "#c3c6cc")

    img.save(OUT, "PNG", optimize=True)


if __name__ == "__main__":
    make_background()
    print(f"DMG background: {OUT}")
