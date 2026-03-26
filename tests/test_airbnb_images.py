import json
import unittest

from app.airbnb_images import _extract_images_from_html, _extract_images_from_json


def _make_deferred_json(picture_urls: list[str]) -> str:
    """Build a minimal deferred-state JSON string containing the given picture URLs."""
    pictures = [{"picture": {"url": url}} for url in picture_urls]
    data = {
        "niobeClientData": [
            [
                "StaysSearch",
                {
                    "data": {
                        "presentation": {
                            "stayProductDetailPage": {
                                "sections": {
                                    "sections": [
                                        {
                                            "section": {
                                                "heroSection": {
                                                    "coverPhoto": {
                                                        "baseUrl": picture_urls[0]
                                                        if picture_urls
                                                        else ""
                                                    },
                                                },
                                                "photos": pictures,
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    }
                },
            ]
        ]
    }
    return json.dumps(data)


class ExtractImagesFromJsonTest(unittest.TestCase):
    def test_old_style_flat_uuid(self) -> None:
        urls = [
            "https://a0.muscache.com/im/pictures/88a4c3f2-b03c-48a0-b951-a0efe7d008d8.jpg",
        ]
        json_text = _make_deferred_json(urls)
        result = _extract_images_from_json(json_text, "12345")
        self.assertEqual(result, urls)

    def test_new_style_hosting_path(self) -> None:
        urls = [
            "https://a0.muscache.com/im/pictures/hosting/Hosting-9262181/original/4d7fff20-ca89-4ddb-afc3-79861201f180.jpeg",
        ]
        json_text = _make_deferred_json(urls)
        result = _extract_images_from_json(json_text, "9262181")
        self.assertEqual(result, urls)

    def test_miso_path_variant(self) -> None:
        urls = [
            "https://a0.muscache.com/im/pictures/miso/Hosting-52467760/original/8d1f5fa6-0503-42ea-90f8-1e26b617149c.jpeg",
        ]
        json_text = _make_deferred_json(urls)
        result = _extract_images_from_json(json_text, "52467760")
        self.assertEqual(result, urls)

    def test_deduplicates_urls(self) -> None:
        urls = [
            "https://a0.muscache.com/im/pictures/abc12345-aaaa-bbbb-cccc-dddddddddddd.jpg",
            "https://a0.muscache.com/im/pictures/abc12345-aaaa-bbbb-cccc-dddddddddddd.jpg",
            "https://a0.muscache.com/im/pictures/def67890-aaaa-bbbb-cccc-dddddddddddd.jpg",
        ]
        json_text = _make_deferred_json(urls)
        result = _extract_images_from_json(json_text, "12345")
        self.assertEqual(len(result), 2)

    def test_caps_at_max_photos(self) -> None:
        urls = [
            f"https://a0.muscache.com/im/pictures/{i:08d}-aaaa-bbbb-cccc-dddddddddddd.jpg"
            for i in range(10)
        ]
        json_text = _make_deferred_json(urls)
        result = _extract_images_from_json(json_text, "12345")
        self.assertEqual(len(result), 6)

    def test_webp_extension(self) -> None:
        urls = [
            "https://a0.muscache.com/im/pictures/hosting/Hosting-123/original/photo.webp",
        ]
        json_text = _make_deferred_json(urls)
        result = _extract_images_from_json(json_text, "123")
        self.assertEqual(result, urls)

    def test_no_images_returns_empty(self) -> None:
        json_text = _make_deferred_json([])
        result = _extract_images_from_json(json_text, "12345")
        self.assertEqual(result, [])


class ExtractImagesFromHtmlTest(unittest.TestCase):
    def test_finds_images_in_html_attributes(self) -> None:
        html = """
        <html><body>
        <img src="https://a0.muscache.com/im/pictures/hosting/Hosting-111/original/photo1.jpeg">
        <img src="https://a0.muscache.com/im/pictures/miso/Hosting-111/original/photo2.jpeg">
        </body></html>
        """
        result = _extract_images_from_html(html, "111")
        self.assertEqual(len(result), 2)

    def test_ignores_non_image_urls(self) -> None:
        html = """
        <a href="https://a0.muscache.com/im/pictures/other-path.json">not an image</a>
        <img src="https://other-cdn.com/photo.jpg">
        """
        result = _extract_images_from_html(html, "123")
        self.assertEqual(result, [])


class ContextualPicturesExtractionTest(unittest.TestCase):
    """Test the extraction logic used in airbnb_search.py for contextualPictures."""

    def _extract(self, raw: dict) -> list[str]:
        """Replicate the extraction from airbnb_search.py using _picture_url."""
        from app.airbnb_search import _picture_url

        return [
            url
            for pic in raw.get("contextualPictures", [])
            if (url := _picture_url(pic))
        ]

    def test_extracts_string_picture_field(self) -> None:
        raw = {
            "contextualPictures": [
                {"picture": "https://a0.muscache.com/im/pictures/photo1.jpg"},
                {"picture": "https://a0.muscache.com/im/pictures/photo2.jpg"},
            ]
        }
        result = self._extract(raw)
        self.assertEqual(len(result), 2)
        self.assertIn("photo1.jpg", result[0])

    def test_extracts_nested_url_field(self) -> None:
        raw = {
            "contextualPictures": [
                {"picture": {"url": "https://a0.muscache.com/im/pictures/photo1.jpg"}},
            ]
        }
        result = self._extract(raw)
        self.assertEqual(result, ["https://a0.muscache.com/im/pictures/photo1.jpg"])

    def test_extracts_nested_baseUrl_fallback(self) -> None:
        raw = {
            "contextualPictures": [
                {
                    "picture": {
                        "baseUrl": "https://a0.muscache.com/im/pictures/photo1.jpg"
                    }
                },
            ]
        }
        result = self._extract(raw)
        self.assertEqual(result, ["https://a0.muscache.com/im/pictures/photo1.jpg"])

    def test_prefers_url_over_baseUrl(self) -> None:
        raw = {
            "contextualPictures": [
                {
                    "picture": {
                        "url": "https://a0.muscache.com/im/pictures/preferred.jpg",
                        "baseUrl": "https://a0.muscache.com/im/pictures/fallback.jpg",
                    }
                },
            ]
        }
        result = self._extract(raw)
        self.assertEqual(result, ["https://a0.muscache.com/im/pictures/preferred.jpg"])

    def test_skips_empty_contextualPictures(self) -> None:
        raw = {"contextualPictures": []}
        self.assertEqual(self._extract(raw), [])

    def test_skips_missing_contextualPictures(self) -> None:
        raw = {}
        self.assertEqual(self._extract(raw), [])

    def test_skips_pictures_without_url(self) -> None:
        raw = {
            "contextualPictures": [
                {"picture": None},
                {"id": "abc123"},  # no picture key at all
                {"picture": "https://a0.muscache.com/im/pictures/good.jpg"},
            ]
        }
        result = self._extract(raw)
        self.assertEqual(result, ["https://a0.muscache.com/im/pictures/good.jpg"])


if __name__ == "__main__":
    unittest.main()
