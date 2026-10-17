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
import urllib.parse
from dataclasses import dataclass, field

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

    @staticmethod
    def generate_phone_formats(parsed_num: phonenumbers.PhoneNumber) -> list[str]:
        """Generates common formatting permutations for global and local search queries."""
        e164 = phonenumbers.format_number(parsed_num, phonenumbers.PhoneNumberFormat.E164)
        national = phonenumbers.format_number(parsed_num, phonenumbers.PhoneNumberFormat.NATIONAL)
        intl = phonenumbers.format_number(parsed_num, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
        digits_only = re.sub(r"\D", "", e164)
        local_digits = digits_only[len(str(parsed_num.country_code)) :]

        formats = [
            e164,                                   # +12125551234
            national,                               # (212) 555-1234
            intl,                                   # +1 212 555 1234
            digits_only,                            # 12125551234
            local_digits,                           # 2125551234
            f"0{local_digits}",                      # 02125551234
        ]
        # Deduplicate preserving order
        seen = set()
        out = []
        for f in formats:
            if f and f not in seen:
                seen.add(f)
                out.append(f)
        return out

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

        # 1. Scraping pasivo multiformato de motores de búsqueda para extraer nombres y redes
        discovered_names: list[str] = []
        discovered_socials: list[str] = []

        # Buscamos variaciones exactas con comillas
        variations = cls.generate_phone_formats(parsed)
        query_parts = "+OR+".join(f'%22{urllib.parse.quote(v)}%22' for v in variations[:3])

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            search_url = f"https://html.duckduckgo.com/html/?q={query_parts}"
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as client:
                ddg_resp = await client.get(search_url)
                if ddg_resp.status_code == 200:
                    html_text = ddg_resp.text
                    # Extraer enlaces y dominios asociados
                    for url_match in re.finditer(r'<a[^>]+class=\"result__url\"[^>]*>([^<]+)</a>', html_text):
                        clean_url = url_match.group(1).strip()
                        if clean_url and not clean_url.startswith("duckduckgo"):
                            discovered_socials.append(clean_url)

                    # Extraer títulos / nombres de contacto que acompañan al número
                    for title_match in re.finditer(r'<a[^>]+class=\"result__snippet\"[^>]*>(.*?)</a>', html_text, re.DOTALL):
                        snippet = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
                        # Extraer posibles nombres en el snippet si contiene palabras capitalizadas
                        possible_names = re.findall(r'\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?\b', snippet)
                        for name in possible_names:
                            if name not in ("WhatsApp Web", "Google Play", "App Store", "Privacy Policy", "Terms Service"):
                                discovered_names.append(name)
        except Exception:
            pass

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
            associated_names=list(set(discovered_names))[:5],
            associated_usernames=list(set(discovered_socials))[:5],
        )
