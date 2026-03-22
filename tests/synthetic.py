from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def save_image(image: Image.Image, path: Path) -> Path:
    image.save(path)
    return path


def complex_diagram() -> Image.Image:
    image = Image.new("RGB", (420, 280), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 30, 130, 90), outline="black", width=4)
    draw.rounded_rectangle((200, 30, 320, 100), radius=18, outline="black", width=4, fill=(205, 226, 248))
    draw.line((134, 60, 196, 60), fill="black", width=4)
    draw.rectangle((220, 130, 330, 195), outline="black", width=4)
    draw.line((80, 94, 80, 150), fill="black", width=4)
    draw.line((80, 150, 216, 150), fill="black", width=4)
    draw.line((200, 225, 300, 225), fill="black", width=4)
    draw.polygon(((300, 215), (320, 225), (300, 235)), fill="black")
    draw.ellipse((350, 20, 390, 60), fill=(220, 80, 80), outline=(220, 80, 80))
    return image


def occluded_box() -> Image.Image:
    image = Image.new("RGB", (220, 180), "white")
    draw = ImageDraw.Draw(image)
    draw.line((30, 30, 92, 30), fill="black", width=4)
    draw.line((108, 30, 170, 30), fill="black", width=4)
    draw.line((30, 30, 30, 130), fill="black", width=4)
    draw.line((170, 30, 170, 130), fill="black", width=4)
    draw.line((30, 130, 170, 130), fill="black", width=4)
    return image


def open_contour() -> Image.Image:
    image = Image.new("RGB", (180, 180), "white")
    draw = ImageDraw.Draw(image)
    draw.line((30, 30, 30, 140), fill="black", width=4)
    draw.line((30, 140, 150, 140), fill="black", width=4)
    draw.line((150, 140, 150, 30), fill="black", width=4)
    return image


def icon_only() -> Image.Image:
    image = Image.new("RGB", (140, 140), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((25, 25, 115, 115), fill=(120, 180, 240), outline=(120, 180, 240))
    return image


def text_box_diagram() -> Image.Image:
    image = Image.new("RGB", (240, 180), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 180, 120), outline="black", width=4)
    return image
