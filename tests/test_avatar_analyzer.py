import io
from PIL import Image
from adapters.avatar_analyzer import AvatarAnalyzer


def _create_sample_image(color: int, size: tuple[int, int] = (100, 100)) -> bytes:
    img = Image.new("RGB", size, color=(color, color, color))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_avatar_analyzer_exact_match():
    img_bytes = _create_sample_image(color=120, size=(128, 128))
    res = AvatarAnalyzer.compare_avatars(img_bytes, img_bytes)

    assert res["matched"] is True
    assert res["hamming_distance"] == 0
    assert res["similarity_percentage"] == 100.0


def test_avatar_analyzer_resized_match():
    # Misma imagen pero redimensionada (128x128 vs 64x64)
    img_1 = _create_sample_image(color=180, size=(128, 128))
    img_2 = _create_sample_image(color=180, size=(64, 64))

    res = AvatarAnalyzer.compare_avatars(img_1, img_2)
    assert res["matched"] is True
    assert res["hamming_distance"] == 0
    assert res["similarity_percentage"] == 100.0


def test_avatar_analyzer_different_patterns():
    # Imagen 1: Mitad izquierda negra, mitad derecha blanca
    img1 = Image.new("L", (100, 100), 255)
    for x in range(50):
        for y in range(100):
            img1.putpixel((x, y), 0)

    # Imagen 2: Mitad superior negra, mitad inferior blanca
    img2 = Image.new("L", (100, 100), 255)
    for x in range(100):
        for y in range(50):
            img2.putpixel((x, y), 0)

    buf1 = io.BytesIO()
    img1.save(buf1, format="PNG")
    buf2 = io.BytesIO()
    img2.save(buf2, format="PNG")

    res = AvatarAnalyzer.compare_avatars(buf1.getvalue(), buf2.getvalue())
    assert res["matched"] is False
    assert res["hamming_distance"] > 10
