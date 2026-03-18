from gopro_gardening.gopro_client import GoProClient


def test_media_list_payload_parses_legacy_shape() -> None:
    client = GoProClient("http://10.5.5.9:8080/videos/DCIM/")
    payload = {
        "media": [
            {
                "d": "100GOPRO",
                "fs": [
                    {"n": "G001.jpg", "s": "123", "cre": "1710000000", "mod": "1710000001"},
                    {"n": "G002.jpg", "s": "456", "cre": "1710000002", "mod": "1710000003"},
                ],
            }
        ]
    }

    files = client._parse_media_list_payload(payload)

    assert [item.filename for item in files] == ["G001.jpg", "G002.jpg"]
    assert files[0].media_dir == "100GOPRO"
    assert files[0].size_bytes == 123
    assert files[0].created_at is not None
