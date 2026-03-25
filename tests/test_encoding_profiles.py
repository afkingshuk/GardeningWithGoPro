from __future__ import annotations

import pytest

from gopro_gardening.main import _resolve_encoding_settings


def test_fast_profile_overrides_preset_and_crf() -> None:
    config = {
        "encoding": {
            "profile": "fast",
            "fps": 24,
            "codec": "libx264",
            "crf": 18,
            "preset": "medium",
            "pixel_format": "yuv420p",
            "output_extension": "mp4",
        }
    }

    resolved = _resolve_encoding_settings(config)

    assert resolved["profile"] == "fast"
    assert resolved["preset"] == "veryfast"
    assert resolved["crf"] == 22


def test_custom_fast_profile_override_is_applied() -> None:
    config = {
        "encoding": {
            "profile": "fast",
            "profiles": {
                "fast": {
                    "preset": "faster",
                    "crf": 24,
                }
            },
        }
    }

    resolved = _resolve_encoding_settings(config)

    assert resolved["profile"] == "fast"
    assert resolved["preset"] == "faster"
    assert resolved["crf"] == 24


def test_invalid_profile_raises() -> None:
    with pytest.raises(ValueError):
        _resolve_encoding_settings({"encoding": {"profile": "turbo"}})
