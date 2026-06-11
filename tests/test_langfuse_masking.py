import unittest

from app.observability.langfuse import mask_sensitive_data


class LangfuseMaskingTests(unittest.TestCase):
    def test_preserves_iso_date(self) -> None:
        self.assertEqual(
            mask_sensitive_data("2026-06-01"),
            "2026-06-01",
        )

    def test_preserves_iso_datetime(self) -> None:
        self.assertEqual(
            mask_sensitive_data("2026-06-01T00:00:00Z"),
            "2026-06-01T00:00:00Z",
        )

    def test_preserves_space_separated_datetime(self) -> None:
        self.assertEqual(
            mask_sensitive_data("created 2026-06-01 00:00:00"),
            "created 2026-06-01 00:00:00",
        )

    def test_masks_international_phone_number(self) -> None:
        self.assertEqual(
            mask_sensitive_data("Call +48 123 456 789"),
            "Call [REDACTED_PHONE]",
        )

    def test_masks_dash_separated_phone_number(self) -> None:
        self.assertEqual(
            mask_sensitive_data("Call 123-456-7890"),
            "Call [REDACTED_PHONE]",
        )

    def test_does_not_mask_short_numeric_identifier(self) -> None:
        self.assertEqual(
            mask_sensitive_data("Order 123-456-78"),
            "Order 123-456-78",
        )


if __name__ == "__main__":
    unittest.main()
