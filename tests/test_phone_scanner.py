import pytest
from adapters.phone_scanner import PhoneScanner


@pytest.mark.asyncio
async def test_phone_scanner_valid_us():
    result = await PhoneScanner.scan("+12125551234", default_region="US")

    assert result.is_valid is True
    assert result.e164 == "+12125551234"
    assert result.country_iso == "US"
    assert result.line_type in ("MOBILE", "FIXED_LINE", "FIXED_OR_MOBILE", "VOIP", "PERSONAL_NUMBER")
    assert "whatsapp" in result.footprint_urls
    assert "telegram" in result.footprint_urls


@pytest.mark.asyncio
async def test_phone_scanner_invalid():
    result = await PhoneScanner.scan("12345")
    assert result.is_valid is False
    assert result.error is not None
