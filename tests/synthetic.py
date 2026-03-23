from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


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


def directional_arrow(direction: str) -> Image.Image:
    image = Image.new("RGB", (220, 220), "white")
    draw = ImageDraw.Draw(image)
    if direction == "right":
        draw.line((40, 110, 150, 110), fill="black", width=6)
        draw.polygon(((150, 98), (180, 110), (150, 122)), fill="black")
        return image
    if direction == "left":
        draw.line((70, 110, 180, 110), fill="black", width=6)
        draw.polygon(((70, 98), (40, 110), (70, 122)), fill="black")
        return image
    if direction == "up":
        draw.line((110, 70, 110, 180), fill="black", width=6)
        draw.polygon(((98, 70), (110, 40), (122, 70)), fill="black")
        return image
    if direction == "down":
        draw.line((110, 40, 110, 150), fill="black", width=6)
        draw.polygon(((98, 150), (110, 180), (122, 150)), fill="black")
        return image
    raise ValueError(f"unsupported direction: {direction}")


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


def paper_like_occluded_box() -> Image.Image:
    def draw(draw: ImageDraw.ImageDraw, scale: int) -> None:
        add_gradient_rect(draw, box=(32, 32, 192, 132), scale=scale, top_color=(234, 240, 252), bottom_color=(207, 224, 246))
        draw.line(scaled_points((32, 32, 108, 32), scale), fill="black", width=7 * scale)
        draw.line(scaled_points((124, 32, 192, 32), scale), fill="black", width=7 * scale)
        draw.line(scaled_points((32, 32, 32, 132), scale), fill="black", width=7 * scale)
        draw.line(scaled_points((192, 32, 192, 132), scale), fill="black", width=7 * scale)
        draw.line(scaled_points((32, 132, 192, 132), scale), fill="black", width=7 * scale)
        occluder = scaled_box((108, 20, 124, 48), scale)
        draw.rounded_rectangle(occluder, radius=5 * scale, fill="white")
        draw.ellipse(inset_box(occluder, scale * 3), fill="black")
    return rasterize_fixture((240, 180), draw, seed=11, blur=0.35, compression_quality=88, noise_sigma=4.0)


def paper_like_weak_gap_conflict() -> Image.Image:
    def draw(draw: ImageDraw.ImageDraw, scale: int) -> None:
        draw.line(scaled_points((24, 62, 90, 62), scale), fill="black", width=5 * scale)
        draw.line(scaled_points((108, 62, 178, 62), scale), fill=(45, 45, 45), width=5 * scale)
        draw.line(scaled_points((98, 34, 98, 88), scale), fill="black", width=4 * scale)
    return rasterize_fixture((220, 120), draw, seed=7, blur=0.6, compression_quality=72, noise_sigma=6.0)


def paper_like_noisy_open_contour() -> Image.Image:
    def draw(draw: ImageDraw.ImageDraw, scale: int) -> None:
        add_gradient_rect(draw, box=(28, 28, 154, 148), scale=scale, top_color=(246, 244, 236), bottom_color=(232, 228, 214))
        draw.line(scaled_points((32, 34, 32, 146), scale), fill="black", width=5 * scale)
        draw.line(scaled_points((32, 146, 150, 146), scale), fill="black", width=5 * scale)
        draw.line(scaled_points((150, 146, 150, 40), scale), fill="black", width=5 * scale)
    return rasterize_fixture((190, 180), draw, seed=29, blur=0.9, compression_quality=74, noise_sigma=6.5)


def paper_like_multisegment_connector() -> Image.Image:
    def draw(draw: ImageDraw.ImageDraw, scale: int) -> None:
        draw.rectangle(scaled_box((24, 28, 92, 72), scale), outline="black", width=5 * scale)
        draw.rectangle(scaled_box((176, 126, 246, 174), scale), outline="black", width=5 * scale)
        points = scaled_points((96, 50, 134, 50, 134, 102, 196, 102, 196, 126), scale)
        draw.line(points, fill="black", width=5 * scale, joint="curve")
    return rasterize_fixture((280, 210), draw, seed=17, blur=0.7, compression_quality=78, noise_sigma=5.5)


def paper_like_mixed_figure() -> Image.Image:
    def draw(draw: ImageDraw.ImageDraw, scale: int) -> None:
        draw.line(scaled_points((20, 28, 124, 28), scale), fill="black", width=7 * scale)
        draw.line(scaled_points((20, 96, 124, 96), scale), fill="black", width=7 * scale)
        draw.line(scaled_points((20, 28, 20, 96), scale), fill="black", width=7 * scale)
        draw.line(scaled_points((124, 28, 124, 96), scale), fill="black", width=7 * scale)
        draw.line(scaled_points((128, 62, 184, 62), scale), fill="black", width=6 * scale)
        draw.ellipse(scaled_box((184, 28, 266, 116), scale), fill=(188, 205, 226))
        draw.ellipse(scaled_box((196, 18, 252, 82), scale), fill=(160, 182, 212))
        draw.ellipse(scaled_box((206, 74, 268, 136), scale), fill=(172, 144, 196))
        for offset in range(7):
            draw.ellipse(scaled_box((188 + offset * 4, 34 + offset * 7, 248 - offset * 3, 118 - offset * 4), scale), outline=(90 + offset * 10, 100, 120 + offset * 6), width=3 * scale)
        blob = scaled_box((198, 46, 244, 98), scale)
        draw.polygon(
            [
                (blob[0], blob[1] + 8 * scale),
                (blob[0] + 18 * scale, blob[1]),
                (blob[2], blob[1] + 10 * scale),
                (blob[2] - 12 * scale, blob[3]),
                (blob[0] + 5 * scale, blob[3] - 10 * scale),
            ],
            fill=(120, 76, 132),
        )
    return rasterize_fixture((300, 170), draw, seed=41, blur=0.45, compression_quality=78, noise_sigma=4.6)


def scaled_box(box: tuple[int, int, int, int], scale: int) -> tuple[int, int, int, int]:
    return tuple(value * scale for value in box)


def inset_box(box: tuple[int, int, int, int], inset: int) -> tuple[int, int, int, int]:
    return (box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset)


def scaled_points(points: tuple[int, ...], scale: int) -> tuple[int, ...]:
    return tuple(value * scale for value in points)


def add_gradient_rect(
    draw: ImageDraw.ImageDraw,
    *,
    box: tuple[int, int, int, int],
    scale: int,
    top_color: tuple[int, int, int],
    bottom_color: tuple[int, int, int],
) -> None:
    left, top, right, bottom = scaled_box(box, scale)
    height = max(1, bottom - top)
    for y in range(top, bottom):
        ratio = (y - top) / height
        color = tuple(
            int(round(top_channel * (1.0 - ratio) + bottom_channel * ratio))
            for top_channel, bottom_channel in zip(top_color, bottom_color, strict=True)
        )
        draw.line((left, y, right, y), fill=color, width=1)


def rasterize_fixture(
    size: tuple[int, int],
    draw_fn,
    *,
    seed: int,
    blur: float,
    compression_quality: int,
    noise_sigma: float,
) -> Image.Image:
    scale = 4
    high_res = Image.new("RGB", (size[0] * scale, size[1] * scale), "white")
    draw_fn(ImageDraw.Draw(high_res), scale)
    image = high_res.resize(size, Image.Resampling.LANCZOS)
    image = image.filter(ImageFilter.GaussianBlur(radius=blur))
    image = apply_noise(image, seed=seed, sigma=noise_sigma)
    image = jpeg_roundtrip(image, quality=compression_quality)
    return image


def apply_noise(image: Image.Image, *, seed: int, sigma: float) -> Image.Image:
    rng = np.random.default_rng(seed)
    array = np.asarray(image, dtype=np.int16)
    noise = rng.normal(0.0, sigma, size=array.shape)
    noisy = np.clip(array + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(noisy)


def jpeg_roundtrip(image: Image.Image, *, quality: int) -> Image.Image:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")
