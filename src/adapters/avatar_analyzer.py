"""Avatar & Profile Picture Forensic Analyzer.

Capabilities:
1. Extract basic EXIF metadata (camera, datetime, dimensions, GPS if present).
2. Compute Perceptual Hash (Difference Hash - dHash) in pure Python (using PIL).
3. Calculate Hamming Distance to determine if two avatar images match across platforms
   even when resized, recompressed or slightly cropped.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS


@dataclass
class AvatarAnalysisResult:
    hash_hex: str
    dimensions: tuple[int, int]
    format: str
    exif_metadata: dict[str, Any] = field(default_factory=dict)
    gps_info: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class AvatarAnalyzer:
    """Forensic image analysis for OSINT investigations."""

    @staticmethod
    def _open_image(source: str | bytes | Path) -> Image.Image:
        if isinstance(source, bytes):
            return Image.open(io.BytesIO(source))
        return Image.open(source)

    @classmethod
    def compute_dhash(cls, source: str | bytes | Path, hash_size: int = 8) -> str:
        """Computes Difference Hash (dHash) of an image.

        1. Grayscale.
        2. Resize to (hash_size + 1, hash_size) ignoring aspect ratio.
        3. Compare adjacent pixels horizontally: 1 if left > right, else 0.
        4. Convert bits to hex string.
        """
        with cls._open_image(source) as img:
            # Convert to grayscale and resize
            resized = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
            pixels: list[int] = [
                int(resized.getpixel((x, y)))  # type: ignore[arg-type]
                for y in range(hash_size)
                for x in range(hash_size + 1)
            ]

            difference = []
            for row in range(hash_size):
                row_start = row * (hash_size + 1)
                for col in range(hash_size):
                    left = pixels[row_start + col]
                    right = pixels[row_start + col + 1]
                    difference.append(left > right)

            # Convert boolean array to hex string
            decimal_value = 0
            for index, value in enumerate(difference):
                if value:
                    decimal_value += 1 << index
            hex_format = f"{decimal_value:0{hash_size * hash_size // 4}x}"
            return hex_format

    @staticmethod
    def hamming_distance(hash1: str, hash2: str) -> int:
        """Calculates bitwise Hamming distance between two hex hashes."""
        if len(hash1) != len(hash2):
            # Pad to equal length
            max_len = max(len(hash1), len(hash2))
            hash1 = hash1.zfill(max_len)
            hash2 = hash2.zfill(max_len)

        i1 = int(hash1, 16)
        i2 = int(hash2, 16)
        xor_val = i1 ^ i2
        return bin(xor_val).count("1")

    @classmethod
    def analyze_image(cls, source: str | bytes | Path) -> AvatarAnalysisResult:
        """Extracts full forensic metadata and perceptual hash."""
        try:
            with cls._open_image(source) as img:
                dimensions = img.size
                img_format = img.format or "UNKNOWN"
                dhash = cls.compute_dhash(source)

                exif_data: dict[str, Any] = {}
                gps_data: dict[str, Any] = {}

                raw_exif = getattr(img, "_getexif", None)
                if callable(raw_exif):
                    exif_dict = raw_exif()
                    if isinstance(exif_dict, dict):
                        for tag_id, value in exif_dict.items():
                            tag_name = TAGS.get(tag_id, str(tag_id))
                            if tag_name == "GPSInfo" and isinstance(value, dict):
                                for gps_id, gps_val in value.items():
                                    sub_name = GPSTAGS.get(gps_id, str(gps_id))
                                    gps_data[sub_name] = str(gps_val)
                            else:
                                exif_data[tag_name] = str(value)

                return AvatarAnalysisResult(
                    hash_hex=dhash,
                    dimensions=dimensions,
                    format=img_format,
                    exif_metadata=exif_data,
                    gps_info=gps_data,
                )
        except Exception as exc:
            return AvatarAnalysisResult(
                hash_hex="",
                dimensions=(0, 0),
                format="UNKNOWN",
                error=str(exc),
            )

    @classmethod
    def compare_avatars(
        cls,
        source1: str | bytes | Path,
        source2: str | bytes | Path,
        match_threshold: int = 10,
    ) -> dict[str, Any]:
        """Compares two avatars and returns similarity metrics."""
        res1 = cls.analyze_image(source1)
        res2 = cls.analyze_image(source2)

        if res1.error or res2.error:
            return {
                "matched": False,
                "error": f"Failed analyzing images: {res1.error or res2.error}",
            }

        distance = cls.hamming_distance(res1.hash_hex, res2.hash_hex)
        max_bits = len(res1.hash_hex) * 4
        similarity = round((1.0 - (distance / max_bits)) * 100, 2)

        return {
            "matched": distance <= match_threshold,
            "hamming_distance": distance,
            "similarity_percentage": similarity,
            "hash1": res1.hash_hex,
            "hash2": res2.hash_hex,
            "dimensions1": res1.dimensions,
            "dimensions2": res2.dimensions,
        }
