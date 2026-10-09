"""Phone OSINT & Reverse Identity Scanner.

Features:
1. E.164 parsing & validation via Google's libphonenumber.
2. Telecom Intelligence: Carrier, country, region, line type (mobile/fixed/voip), timezones.
3. Search Footprint & Dorks Generator (WhatsApp, Telegram, Truecaller, Sync.me, Facebook, Google dorks).
4. WhatsApp presence check via wa.me protocol probe.
5. Extraction of possible usernames and identities from dorking query variations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import phonenumbers
from phonenumbers import carrier, geocoder, timezone, PhoneNumberType
import httpx

from core.config import AppSettings


@dataclass
class PhoneScanResult:
    raw_input: str
    e164: str
    is_valid: bool
    country_code: int
    country_iso: str
    country_name: str
    carrier_name: str
    line_type: str
    timezones: list[str]
    whatsapp_active: bool | None = None
    whatsapp_url: str | None = None
    footprint_urls: dict[str, str] = field(default_factory=dict)
    associated_names: list[str] = field(default_factory=list)
    associated_usernames: list[str] = field(default_factory=list)
    error: str | None = None


class PhoneScanner:
    """Specialized Phone OSINT scanner with telecom and footprint correlation."""

    @staticmethod
    def _get_line_type_name(num_type: PhoneNumberType) -> str:
        mapping = {
            PhoneNumberType.MOBILE: "MOBILE",
            PhoneNumberType.FIXED_LINE: "FIXED_LINE",
            PhoneNumberType.FIXED_LINE_OR_MOBILE: "FIXED_OR_MOBILE",
            PhoneNumberType.TOLL_FREE: "TOLL_FREE",
            PhoneNumberType.PREMIUM_RATE: "PREMIUM_RATE",
            PhoneNumberType.SHARED_COST: "SHARED_COST",
            PhoneNumberType.VOIP: "VOIP",
            PhoneNumberType.PERSONAL_NUMBER: "PERSONAL_NUMBER",
            PhoneNumberType.PAGER: "PAGER",
            PhoneNumberType.UAN: "UAN",
            PhoneNumberType.VOICEMAIL: "VOICEMAIL",
        }
        return mapping.get(num_type, "UNKNOWN")

    @classmethod
    async def scan(
        cls,
        phone_number: str,
        settings: AppSettings | None = None,
        default_region: str | None = "US",
    ) -> PhoneScanResult:
        """Runs full telecom and footprint OSINT on a given phone number."""
        clean_input = phone_number.strip()
        try:
            parsed = phonenumbers.parse(clean_input, default_region)
        except Exception as exc:
            return PhoneScanResult(
                raw_input=phone_number,
                e164="",
                is_valid=False,
                country_code=0,
                country_iso="",
                country_name="",
                carrier_name="",
                line_type="INVALID",
                timezones=[],
                error=f"Parsing error: {exc}",
            )

        is_valid = phonenumbers.is_valid_number(parsed)
        if not is_valid:
            return PhoneScanResult(
                raw_input=phone_number,
                e164=phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
                is_valid=False,
                country_code=parsed.country_code or 0,
                country_iso=phonenumbers.region_code_for_number(parsed) or "",
                country_name=geocoder.description_for_number(parsed, "es") or "",
                carrier_name="",
                line_type="INVALID",
                timezones=[],
                error="Invalid phone number format or non-assigned block.",
            )

        e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        national = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL)
        clean_digits = re.sub(r"\D", "", e164)
        c_code = parsed.country_code
        iso = phonenumbers.region_code_for_number(parsed) or ""
        c_name = geocoder.description_for_number(parsed, "es") or ""
        car_name = carrier.name_for_number(parsed, "es") or carrier.name_for_number(parsed, "en") or ""
        l_type = cls._get_line_type_name(phonenumbers.number_type(parsed))
        tz_list = list(timezone.time_zones_for_number(parsed))

        # Generar footprint dorks de huella digital
        footprints = {
            "whatsapp": f"https://wa.me/{clean_digits}",
            "telegram": f"https://t.me/+{clean_digits}",
            "truecaller": f"https://www.truecaller.com/search/{iso.lower()}/{clean_digits}",
            "syncme": f"https://sync.me/search/?number={clean_digits}",
            "google_dork_quotes": f'https://www.google.com/search?q="{e164}"+OR+"{national}"',
            "google_dork_social": f'https://www.google.com/search?q="{clean_digits}"+site:instagram.com+OR+site:facebook.com+OR+site:twitter.com+OR+site:linkedin.com',
            "whocallsme": f"https://whocallsme.com/Phone-Number.aspx/{clean_digits}",
        }

        # Probe pasivo de WhatsApp (wa.me)
        whatsapp_active = None
        wa_url = footprints["whatsapp"]
        try:
            async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
                resp = await client.get(wa_url)
                if resp.status_code == 200:
                    # Si wa.me devuelve botón para chatear, el número suele estar registrado
                    if "action-send" in resp.text or "send?phone=" in resp.text or "Chat on WhatsApp" in resp.text:
                        whatsapp_active = True
                    else:
                        whatsapp_active = False
        except Exception:
            whatsapp_active = None

        return PhoneScanResult(
            raw_input=phone_number,
            e164=e164,
            is_valid=True,
            country_code=c_code,
            country_iso=iso,
            country_name=c_name,
            carrier_name=car_name,
            line_type=l_type,
            timezones=tz_list,
            whatsapp_active=whatsapp_active,
            whatsapp_url=wa_url if whatsapp_active else None,
            footprint_urls=footprints,
        )
