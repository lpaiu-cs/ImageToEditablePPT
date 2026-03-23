from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


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


def paper_like_directional_arrow(direction: str) -> Image.Image:
    def draw(draw: ImageDraw.ImageDraw, scale: int) -> None:
        shaft_color = (42, 42, 42)
        head_color = (18, 18, 18)
        shaft_width = 6 * scale
        if direction == "right":
            draw.line(scaled_points((40, 110, 150, 110), scale), fill=shaft_color, width=shaft_width)
            draw.polygon(((150 * scale, 98 * scale), (180 * scale, 110 * scale), (150 * scale, 122 * scale)), fill=head_color)
            return
        if direction == "left":
            draw.line(scaled_points((70, 110, 180, 110), scale), fill=shaft_color, width=shaft_width)
            draw.polygon(((70 * scale, 98 * scale), (40 * scale, 110 * scale), (70 * scale, 122 * scale)), fill=head_color)
            return
        if direction == "up":
            draw.line(scaled_points((110, 70, 110, 180), scale), fill=shaft_color, width=shaft_width)
            draw.polygon(((98 * scale, 70 * scale), (110 * scale, 40 * scale), (122 * scale, 70 * scale)), fill=head_color)
            return
        if direction == "down":
            draw.line(scaled_points((110, 40, 110, 150), scale), fill=shaft_color, width=shaft_width)
            draw.polygon(((98 * scale, 150 * scale), (110 * scale, 180 * scale), (122 * scale, 150 * scale)), fill=head_color)
            return
        raise ValueError(f"unsupported direction: {direction}")

    return rasterize_fixture((220, 220), draw, seed={"right": 61, "left": 62, "up": 63, "down": 64}[direction], blur=0.2, compression_quality=90, noise_sigma=1.0)


def paper_like_insufficient_widening() -> Image.Image:
    def draw(draw: ImageDraw.ImageDraw, scale: int) -> None:
        draw.line(scaled_points((40, 110, 160, 110), scale), fill=(36, 36, 36), width=6 * scale)
        draw.polygon(((160 * scale, 102 * scale), (176 * scale, 110 * scale), (160 * scale, 118 * scale)), fill=(20, 20, 20))

    return rasterize_fixture((220, 220), draw, seed=71, blur=0.2, compression_quality=90, noise_sigma=1.0)


def paper_like_symmetric_wedge() -> Image.Image:
    def draw(draw: ImageDraw.ImageDraw, scale: int) -> None:
        draw.line(scaled_points((40, 110, 146, 110), scale), fill=(36, 36, 36), width=6 * scale)
        draw.polygon(((146 * scale, 94 * scale), (176 * scale, 110 * scale), (146 * scale, 126 * scale), (116 * scale, 110 * scale)), fill=(18, 18, 18))

    return rasterize_fixture((220, 220), draw, seed=72, blur=0.22, compression_quality=89, noise_sigma=1.2)


def paper_like_noisy_line_ending() -> Image.Image:
    def draw(draw: ImageDraw.ImageDraw, scale: int) -> None:
        draw.line(scaled_points((34, 110, 164, 110), scale), fill=(38, 38, 38), width=5 * scale)
        for x, y, radius in ((166, 102, 3), (172, 109, 4), (168, 118, 3), (176, 104, 2), (178, 115, 2)):
            draw.ellipse(((x - radius) * scale, (y - radius) * scale, (x + radius) * scale, (y + radius) * scale), fill=(52, 52, 52))

    return rasterize_fixture((220, 220), draw, seed=73, blur=0.45, compression_quality=79, noise_sigma=3.2)


def paper_like_mixed_arrow_with_connector() -> Image.Image:
    def draw(draw: ImageDraw.ImageDraw, scale: int) -> None:
        draw.line(scaled_points((28, 48, 110, 48), scale), fill=(30, 30, 30), width=5 * scale)
        draw.line(scaled_points((42, 132, 118, 132), scale), fill=(40, 40, 40), width=6 * scale)
        draw.polygon(((118 * scale, 118 * scale), (150 * scale, 132 * scale), (118 * scale, 146 * scale)), fill=(20, 20, 20))
        draw.line(scaled_points((184, 44, 184, 90), scale), fill=(34, 34, 34), width=5 * scale)
        draw.line(scaled_points((184, 90, 246, 90), scale), fill=(34, 34, 34), width=5 * scale)

    return rasterize_fixture((300, 180), draw, seed=74, blur=0.2, compression_quality=90, noise_sigma=1.2)


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


def boxed_text_cluster_diagram() -> Image.Image:
    image = Image.new("RGB", (320, 220), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.rectangle((34, 34, 286, 176), outline="black", width=5)
    draw.text((76, 88), "Encoder Stage", fill=(26, 26, 26), font=font)
    draw.text((88, 110), "Token Mixer", fill=(30, 30, 30), font=font)
    image = image.filter(ImageFilter.GaussianBlur(radius=0.35))
    image = apply_noise(image, seed=83, sigma=1.2)
    return jpeg_roundtrip(image, quality=88)


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


def paper_like_text_occluded_connector_graph() -> Image.Image:
    def draw(draw: ImageDraw.ImageDraw, scale: int) -> None:
        font = ImageFont.load_default()
        draw.rectangle(scaled_box((28, 34, 94, 78), scale), outline="black", width=5 * scale)
        draw.rectangle(scaled_box((222, 138, 292, 184), scale), outline="black", width=5 * scale)
        draw.line(scaled_points((96, 56, 154, 56), scale), fill="black", width=5 * scale)
        draw.line(scaled_points((154, 56, 154, 112), scale), fill="black", width=5 * scale)
        draw.line(scaled_points((154, 112, 242, 112), scale), fill="black", width=5 * scale)
        label = scaled_box((136, 94, 208, 130), scale)
        draw.rounded_rectangle(label, radius=8 * scale, fill=(250, 250, 250))
        draw.text((label[0] + 10 * scale, label[1] + 10 * scale), "bridge", fill=(28, 28, 28), font=font)
        draw.line(scaled_points((242, 112, 242, 138), scale), fill="black", width=5 * scale)

    return rasterize_fixture((330, 220), draw, seed=18, blur=0.55, compression_quality=80, noise_sigma=3.8)


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


def paper_like_dense_text_diagram() -> Image.Image:
    image = Image.new("RGB", (1280, 820), (249, 249, 246))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    for y in range(image.size[1]):
        ratio = y / max(1, image.size[1] - 1)
        color = (
            int(round(248 * (1.0 - ratio) + 240 * ratio)),
            int(round(249 * (1.0 - ratio) + 244 * ratio)),
            int(round(246 * (1.0 - ratio) + 238 * ratio)),
        )
        draw.line((0, y, image.size[0], y), fill=color, width=1)
    draw.rounded_rectangle((70, 70, 560, 360), radius=26, outline=(24, 24, 24), width=8, fill=(235, 241, 248))
    draw.rounded_rectangle((760, 108, 1210, 430), radius=24, outline=(28, 28, 28), width=8, fill=(245, 239, 228))
    draw.rectangle((210, 510, 600, 710), outline=(22, 22, 22), width=7, fill=(240, 245, 234))
    draw.line((560, 214, 760, 214), fill=(20, 20, 20), width=8)
    draw.line((406, 360, 406, 510), fill=(20, 20, 20), width=8)
    draw.line((406, 510, 210, 510), fill=(20, 20, 20), width=8)
    draw.line((986, 430, 986, 520), fill=(20, 20, 20), width=8)
    draw.line((986, 520, 610, 520), fill=(20, 20, 20), width=8)
    left_rows = [
        "Input tokens",
        "Patch embedding",
        "Residual stream",
        "Normalization",
        "Attention block",
        "Projection head",
    ]
    right_rows = [
        "Skip branch",
        "Feature mixer",
        "Context block",
        "Gated update",
        "Dense labels",
        "Render path",
    ]
    lower_rows = [
        "Prediction logits",
        "Loss terms",
        "Auxiliary score",
        "Regularizer alpha",
    ]
    for index, text in enumerate(left_rows):
        draw.text((118, 106 + index * 28), text, fill=(36, 36, 36), font=font)
    for index, text in enumerate(right_rows):
        draw.text((806, 150 + index * 30), text, fill=(40, 40, 40), font=font)
    for index, text in enumerate(lower_rows):
        draw.text((254, 560 + index * 28), text, fill=(34, 34, 34), font=font)
    for row in range(7):
        draw.text((640, 86 + row * 26), f"legend {row + 1}", fill=(54, 54, 54), font=font)
    for row in range(6):
        draw.text((72, 392 + row * 24), f"caption row {row + 1}", fill=(64, 64, 64), font=font)
    for row in range(5):
        draw.text((830, 468 + row * 24), f"footnote {row + 1}", fill=(60, 60, 60), font=font)
    draw.ellipse((1090, 560, 1215, 700), fill=(184, 206, 231))
    draw.ellipse((1110, 540, 1238, 640), fill=(165, 182, 216))
    draw.ellipse((1060, 622, 1188, 742), fill=(196, 146, 194))
    draw.polygon([(1106, 586), (1142, 556), (1204, 570), (1190, 628), (1124, 642)], fill=(120, 86, 138))
    for x, y, radius in ((1040, 180, 18), (1072, 214, 12), (1112, 174, 10), (990, 648, 16), (1160, 734, 12)):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(170, 180, 198))
    for x0, y0, x1, y1, shade in ((92, 96, 538, 344, 6), (782, 130, 1188, 404, 8), (224, 526, 584, 694, 7)):
        for offset in range(3):
            draw.rounded_rectangle((x0 + offset * 6, y0 + offset * 6, x1 - offset * 6, y1 - offset * 6), radius=18, outline=(220 - shade * offset, 220 - shade * offset, 220 - shade * offset), width=1)
    image = image.filter(ImageFilter.GaussianBlur(radius=0.55))
    image = apply_noise(image, seed=84, sigma=3.8)
    return jpeg_roundtrip(image, quality=76)


def paper_like_line_with_attached_label_blob() -> Image.Image:
    def draw(draw: ImageDraw.ImageDraw, scale: int) -> None:
        draw.rectangle(scaled_box((34, 72, 118, 138), scale), outline=(24, 24, 24), width=6 * scale)
        draw.line(scaled_points((120, 105, 316, 105), scale), fill=(26, 26, 26), width=6 * scale)
        draw.rounded_rectangle(scaled_box((186, 84, 242, 126), scale), radius=7 * scale, fill=(32, 32, 32))
        draw.rectangle(scaled_box((206, 70, 220, 88), scale), fill=(28, 28, 28))
        draw.rectangle(scaled_box((226, 86, 238, 116), scale), fill=(36, 36, 36))

    return rasterize_fixture((360, 220), draw, seed=85, blur=0.35, compression_quality=84, noise_sigma=2.1)


def paper_like_outer_contour_box_with_label() -> Image.Image:
    image = Image.new("RGB", (420, 280), (248, 248, 244))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    add_gradient_rect(
        draw,
        box=(56, 48, 348, 214),
        scale=1,
        top_color=(236, 241, 247),
        bottom_color=(229, 236, 244),
    )
    draw.rounded_rectangle((54, 46, 350, 216), radius=24, outline=(28, 28, 28), width=6)
    draw.rounded_rectangle((138, 34, 278, 86), radius=10, fill=(34, 34, 34))
    draw.text((166, 50), "STM cache", fill=(252, 252, 252), font=font)
    draw.text((108, 112), "query route", fill=(48, 48, 48), font=font)
    draw.text((110, 138), "context merge", fill=(48, 48, 48), font=font)
    draw.line((350, 132, 396, 132), fill=(26, 26, 26), width=6)
    draw.rectangle((190, 208, 214, 238), fill=(32, 32, 32))
    image = image.filter(ImageFilter.GaussianBlur(radius=0.45))
    image = apply_noise(image, seed=86, sigma=2.4)
    return jpeg_roundtrip(image, quality=82)


def paper_like_filled_panel_without_border() -> Image.Image:
    image = Image.new("RGB", (420, 280), (247, 246, 241))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    add_gradient_rect(
        draw,
        box=(60, 42, 350, 214),
        scale=1,
        top_color=(231, 239, 248),
        bottom_color=(219, 229, 241),
    )
    draw.rounded_rectangle((58, 40, 352, 216), radius=28, fill=(226, 235, 246))
    draw.rounded_rectangle((126, 26, 274, 84), radius=12, fill=(42, 54, 76))
    draw.text((162, 48), "Cache block", fill=(250, 250, 250), font=font)
    draw.text((112, 118), "context route", fill=(56, 62, 74), font=font)
    draw.text((112, 146), "residual gate", fill=(56, 62, 74), font=font)
    image = image.filter(ImageFilter.GaussianBlur(radius=0.55))
    image = apply_noise(image, seed=87, sigma=2.8)
    return jpeg_roundtrip(image, quality=80)


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
