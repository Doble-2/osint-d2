import pytest
from adapters.phone_scanner import PhoneScanner


@pytest.mark.asyncio
async def test_phone_scanner_valid_venezuela():
    result = await PhoneScanner.scan("+584241922882")

    assert result.is_valid is True
    assert result.e164 == "+584241922882"
    assert result.country_iso == "VE"
    assert "Venezuela" in result.country_name
    assert result.carrier_name.lower() == "movistar"
    assert result.line_type in ("MOBILE", "FIXED_OR_MOBILE")
    assert "America/Caracas" in result.timezones
    assert "whatsapp" in result.footprint_urls
    assert "telegram" in result.footprint_urls


@pytest.mark.asyncio
async def test_phone_scanner_invalid():
    result = await PhoneScanner.scan("12345")
    assert result.is_valid is False
    assert result.error is not None
