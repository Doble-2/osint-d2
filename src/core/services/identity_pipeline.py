"""Identity scanning orchestration utilities.

This module consolidates the OSINT scanning flow that was previously
scattered across the CLI layer. The CLI now delegates all aggregation
concerns to these helpers, which makes the pipeline reusable for future
entry-points (APIs, batch jobs, tests) and keeps side-effects (printing,
progress bars) out of the core logic.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

from adapters.email_sources import (
    GravatarProfileScanner,
    GravatarScanner,
    OpenPGPKeysScanner,
    UbuntuKeyserverScanner,
)
from adapters.osint_sources import (
    AboutMeScanner,
    BehanceScanner,
    DevToScanner,
    DribbbleScanner,
    GitHubGistScanner,
    GitHubScanner,
    GitLabScanner,
    KaggleScanner,
    KeybaseScanner,
    MediumScanner,
    NpmScanner,
    PinterestScanner,
    ProductHuntScanner,
    RedditScanner,
    SoundCloudScanner,
    TelegramScanner,
    TwitchScanner,
    XScanner,
)
from adapters.profile_enricher import enrich_profiles_from_html
from adapters.site_lists import (
    load_email_sites,
    load_username_sites,
    run_email_sites,
    run_username_sites,
)
from adapters.sherlock_runner import run_sherlock_username
from core.config import AppSettings
from core.domain.models import PersonEntity, SocialProfile
from core.resources_loader import get_default_list_path, load_sherlock_data


@dataclass
class SiteListOptions:
    """Configuration for the site-lists engine (WhatsMyName style)."""

    enabled: bool = False
    username_path: Path | None = None
    email_path: Path | None = None
    max_concurrency: int | None = None
    categories: set[str] | None = None
    no_nsfw: bool | None = None


@dataclass
class HuntRequest:
    """Parameters that control the hunt pipeline."""

    usernames: Sequence[str] | None = None
    emails: Sequence[str] | None = None
    scan_localpart: bool = True
    site_lists: SiteListOptions = field(default_factory=SiteListOptions)
    use_sherlock: bool = False
    strict: bool = False
    sherlock_manifest: dict[str, object] | None = None


@dataclass
class PipelineHooks:
    """Optional callbacks for UI layers (progress, warnings)."""

    warning: Callable[[str], None] | None = None
    sherlock_start: Callable[[int], None] | None = None
    sherlock_progress: Callable[[int, int, str], None] | None = None


@dataclass
class PipelineResult:
    """Output of a pipeline invocation."""

    person: PersonEntity
    usernames: list[str]
    emails: list[str]
    warnings: list[str] = field(default_factory=list)


_USERNAME_SCANNERS = (
    GitHubScanner,
    GitHubGistScanner,
    GitLabScanner,
    KeybaseScanner,
    DevToScanner,
    MediumScanner,
    NpmScanner,
    ProductHuntScanner,
    RedditScanner,
    TwitchScanner,
    TelegramScanner,
    AboutMeScanner,
    PinterestScanner,
    SoundCloudScanner,
    KaggleScanner,
    DribbbleScanner,
    BehanceScanner,
    XScanner,
)

_EMAIL_SCANNERS = (
    GravatarScanner,
    GravatarProfileScanner,
    OpenPGPKeysScanner,
    UbuntuKeyserverScanner,
)

_STRICT_SHERLOCK_DENYLIST: set[str] = {
    "avizo",
    "fanpop",
    "hubski",
}

_STRICT_SUSPICIOUS_URL_PARTS: tuple[str, ...] = (
    "login",
    "sign_in",
    "consent",
    "privacy",
    "cookie",
    "redirect",
    "return_url=",
    "callbackurl=",
    "search?",
    "search/?",
    "vendor_not_found",
    "nastaveni-souhlasu",
)


def sanitize_target_for_filename(value: str) -> str:
    """Generate a filesystem-friendly slug for reports."""

    out: list[str] = []
    for ch in value.strip():
        if ch.isalnum() or ch in ("-", "_", "."):
            out.append(ch)
        elif ch in ("@", "+"):
            out.append("_")
        else:
            out.append("-")
    cleaned = "".join(out).strip("-_")
    return cleaned or "target"


def dedupe_profiles(profiles: Iterable[SocialProfile]) -> list[SocialProfile]:
    """Remove duplicated profiles keeping the first occurrence."""

    seen: set[tuple[str, str, str]] = set()
    deduped: list[SocialProfile] = []
    for profile in profiles:
        key = (profile.network_name, profile.username, str(profile.url))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(profile)
    return deduped


def _strict_keep_profile(*, profile: SocialProfile, username: str) -> bool:
    if not profile.existe:
        return False

    metadata = profile.metadata if isinstance(profile.metadata, dict) else {}
    if metadata.get("source") != "sherlock":
        return True

    if profile.network_name in _STRICT_SHERLOCK_DENYLIST:
        return False

    final_url = str(metadata.get("final_url") or profile.url).lower()
    if any(part in final_url for part in _STRICT_SUSPICIOUS_URL_PARTS):
        return False

    username_l = username.lower()
    if username_l in final_url:
        return True

    title = metadata.get("title")
    if isinstance(title, str) and username_l in title.lower():
        return True

    description = metadata.get("meta_description")
    if isinstance(description, str) and username_l in description.lower():
        return True

    return False


async def hunt(
    *,
    settings: AppSettings,
    request: HuntRequest,
    hooks: PipelineHooks | None = None,
) -> PipelineResult:
    hooks = hooks or PipelineHooks()
    warnings: list[str] = []

    usernames = list({u.strip() for u in request.usernames or [] if u.strip()})
    emails = list({e.strip().lower() for e in request.emails or [] if e.strip()})

    username_scanners = [scanner() for scanner in _USERNAME_SCANNERS]
    email_scanners = [scanner() for scanner in _EMAIL_SCANNERS]

    profiles: list[SocialProfile] = []
    all_usernames = set(usernames)
    all_emails = set(emails)
    scanned_usernames: set[str] = set()
    scanned_emails: set[str] = set()

    async def safe_scan(
        scanner: object,
        value: str,
        *,
        derived_from: str | None = None,
    ) -> list[SocialProfile]:
        name = scanner.__class__.__name__
        network = name.removesuffix("Scanner").lower()
        try:
            result = await scanner.scan(value)  # type: ignore[attr-defined]
            collected: list[SocialProfile]
            if isinstance(result, list):
                collected = result
            else:
                collected = [result]
            for profile in collected:
                if derived_from and isinstance(profile.metadata, dict):
                    profile.metadata = {**profile.metadata, "derived_from": derived_from}
                if isinstance(profile.url, str) and "example.invalid/x/" in profile.url:
                    profile.url = profile.url.replace("example.invalid/x/", "x.com/")
            return collected
        except Exception as exc:  # pragma: no cover - defensive fallback
            fallback_url = f"https://{network}.com/{value}"
            if network == "x":
                fallback_url = f"https://x.com/{value}"
            metadata: dict[str, object] = {"error": str(exc), "scanner": name}
            if derived_from:
                metadata["derived_from"] = derived_from
            return [
                SocialProfile(
                    url=fallback_url,
                    username=value,
                    network_name=network,
                    existe=False,
                    metadata=metadata,
                )
            ]

    def extract_extras(perfiles: Iterable[SocialProfile]) -> tuple[set[str], set[str]]:
        extra_usernames: set[str] = set()
        extra_emails: set[str] = set()
        for profile in perfiles:
            metadata = profile.metadata if isinstance(profile.metadata, dict) else {}
            for key in ("other_emails", "emails", "email"):
                val = metadata.get(key)
                if isinstance(val, str):
                    extra_emails.add(val)
                elif isinstance(val, list):
                    extra_emails.update([v for v in val if isinstance(v, str)])
            for key in ("other_users", "usernames"):
                val = metadata.get(key)
                if isinstance(val, str):
                    extra_usernames.add(val)
                elif isinstance(val, list):
                    extra_usernames.update([v for v in val if isinstance(v, str)])
            for key in ("other_websites", "websites", "website"):
                val = metadata.get(key)
                if isinstance(val, str) and not val.startswith("http"):
                    extra_usernames.add(val)
                elif isinstance(val, list):
                    for v in val:
                        if isinstance(v, str) and not v.startswith("http"):
                            extra_usernames.add(v)
        cleaned_emails = {e.strip().lower() for e in extra_emails if e and "@" in e}
        cleaned_usernames = {u.strip() for u in extra_usernames if u.strip()}
        return cleaned_usernames, cleaned_emails

    while True:
        new_usernames = list(all_usernames - scanned_usernames)
        new_emails = list(all_emails - scanned_emails)
        if not new_usernames and not new_emails:
            break

        if new_usernames:
            scan_tasks = [
                safe_scan(scanner, username)
                for username in new_usernames
                for scanner in username_scanners
            ]
            scan_results = await asyncio.gather(*scan_tasks)
            for result in scan_results:
                profiles.extend(result)
            scanned_usernames.update(new_usernames)

        if new_emails:
            email_tasks = [
                safe_scan(scanner, email)
                for email in new_emails
                for scanner in email_scanners
            ]
            email_results = await asyncio.gather(*email_tasks)
            for result in email_results:
                profiles.extend(result)
            scanned_emails.update(new_emails)

            if request.scan_localpart:
                localparts = [email.split("@", 1)[0] for email in new_emails]
                local_tasks = [
                    safe_scan(scanner, localpart, derived_from="email_localpart")
                    for localpart in localparts
                    for scanner in username_scanners
                ]
                local_results = await asyncio.gather(*local_tasks)
                for result in local_results:
                    profiles.extend(result)
                all_usernames.update(localparts)

        extra_usernames, extra_emails = extract_extras(profiles)
        all_usernames.update(extra_usernames)
        all_emails.update(extra_emails)

    usernames = sorted(all_usernames)
    emails = sorted(all_emails)

    max_concurrency = request.site_lists.max_concurrency or settings.sites_max_concurrency
    no_nsfw_effective = (
        settings.sites_no_nsfw
        if request.site_lists.no_nsfw is None
        else request.site_lists.no_nsfw
    )

    if request.site_lists.enabled:
        if usernames:
            username_path = request.site_lists.username_path
            if username_path and not username_path.exists():
                fallback = get_default_list_path(username_path.name)
                if fallback:
                    username_path = fallback
            if not username_path or not username_path.exists():
                message = "Site-lists for usernames not configured (missing path)."
                warnings.append(message)
                if hooks.warning:
                    hooks.warning(message)
            else:
                sites_file = load_username_sites(username_path)
                profiles.extend(
                    await run_username_sites(
                        usernames=usernames,
                        sites=sites_file.sites,
                        settings=settings,
                        max_concurrency=max_concurrency,
                        categories=request.site_lists.categories,
                        no_nsfw=no_nsfw_effective,
                    )
                )
        if emails:
            email_path = request.site_lists.email_path
            if email_path and not email_path.exists():
                fallback = get_default_list_path(email_path.name)
                if fallback:
                    email_path = fallback
            if not email_path or not email_path.exists():
                message = "Site-lists for emails not configured (missing path)."
                warnings.append(message)
                if hooks.warning:
                    hooks.warning(message)
            else:
                sites_file = load_email_sites(email_path)
                profiles.extend(
                    await run_email_sites(
                        emails=emails,
                        sites=sites_file.sites,
                        settings=settings,
                        max_concurrency=max_concurrency,
                        categories=request.site_lists.categories,
                        no_nsfw=no_nsfw_effective,
                    )
                )

    if request.use_sherlock and usernames:
        manifest = request.sherlock_manifest or load_sherlock_data(refresh=False)
        total = 0
        for username in usernames:
            for site_name, info in manifest.items():
                if site_name == "$schema":
                    continue
                if not isinstance(info, dict):
                    continue
                if no_nsfw_effective and bool(info.get("isNSFW")):
                    continue
                total += 1
        if total and hooks.sherlock_start:
            hooks.sherlock_start(total)

        progress_cb = hooks.sherlock_progress if total else None
        profiles.extend(
            await run_sherlock_username(
                usernames=usernames,
                manifest=manifest,
                settings=settings,
                max_concurrency=max_concurrency,
                no_nsfw=no_nsfw_effective,
                progress_callback=progress_cb,
            )
        )

    profiles = dedupe_profiles(profiles)

    if request.strict and usernames:
        profiles = [
            profile
            for profile in profiles
            if any(_strict_keep_profile(profile=profile, username=username) for username in usernames)
        ]

    await enrich_profiles_from_html(
        profiles=profiles,
        settings=settings,
        max_concurrency=min(20, max_concurrency),
    )

    extra_usernames, extra_emails = extract_extras(profiles)
    usernames = sorted({*usernames, *extra_usernames})
    emails = sorted({*emails, *extra_emails})

    target_parts = []
    if usernames:
        target_parts.append("/".join(usernames))
    if emails:
        target_parts.append("/".join(emails))
    target_label = "/".join(target_parts) or "target"

    person = PersonEntity(target=target_label, profiles=profiles)

    return PipelineResult(
        person=person,
        usernames=usernames,
        emails=emails,
        warnings=warnings,
    )


async def scan_username(
    *,
    settings: AppSettings,
    username: str,
    hooks: PipelineHooks | None = None,
) -> PipelineResult:
    request = HuntRequest(
        usernames=[username],
        emails=[],
        scan_localpart=False,
        site_lists=SiteListOptions(enabled=False),
        use_sherlock=False,
        strict=False,
    )
    return await hunt(settings=settings, request=request, hooks=hooks)


async def scan_email(
    *,
    settings: AppSettings,
    email: str,
    scan_localpart: bool,
    hooks: PipelineHooks | None = None,
) -> PipelineResult:
    request = HuntRequest(
        usernames=[],
        emails=[email],
        scan_localpart=scan_localpart,
        site_lists=SiteListOptions(enabled=False),
        use_sherlock=False,
        strict=False,
    )
    return await hunt(settings=settings, request=request, hooks=hooks)
