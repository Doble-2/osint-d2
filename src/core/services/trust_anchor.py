"""Trust-anchor identity verification.

"Ground truth" anchors let the user declare which profiles are *known*
to belong to the target (e.g. ``--trust instagram:xkissmely``).

Workflow:
1.  **Build reference** — scan trusted sources first to collect identity
    signals: display name, bio keywords, avatar hash.
2.  **Verify profiles** — after scanning all networks, compare each
    result against the reference.  Profiles that clearly belong to a
    different person are flagged ``verified=False``.

Multiple trust anchors are supported and their signals are merged.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field

from core.domain.models import SocialProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class TrustAnchor:
    """A single user-declared source of truth."""
    network: str
    username: str

    @classmethod
    def parse(cls, raw: str) -> "TrustAnchor":
        """Parse ``network:username`` or ``email:user@domain`` string.

        Examples::

            TrustAnchor.parse("instagram:xkissmely")
            TrustAnchor.parse("github:doble-2")
            TrustAnchor.parse("email:kissmelymarcano@gmail.com")
        """
        if ":" not in raw:
            raise ValueError(
                f"Invalid trust anchor '{raw}'. Expected format: network:username"
            )
        network, username = raw.split(":", 1)
        return cls(
            network=network.strip().lower(),
            username=username.strip(),
        )

    @property
    def is_email(self) -> bool:
        return self.network == "email" and "@" in self.username


@dataclass
class ReferenceIdentity:
    """Identity signals extracted from trusted profiles."""
    names: set[str] = field(default_factory=set)
    bio_keywords: set[str] = field(default_factory=set)
    avatar_hashes: set[str] = field(default_factory=set)
    emails: set[str] = field(default_factory=set)
    locations: set[str] = field(default_factory=set)
    trusted_networks: dict[str, str] = field(default_factory=dict)
    # Map of network -> username for trusted profiles

    def is_empty(self) -> bool:
        return not self.names and not self.bio_keywords and not self.avatar_hashes and not self.emails


# ---------------------------------------------------------------------------
# Reference builder
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Lowercase and strip accents/special chars for fuzzy comparison."""
    text = text.lower().strip()
    # Remove common HTML entities and special chars
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return text


def _extract_keywords(text: str, *, min_len: int = 3) -> set[str]:
    """Extract meaningful keywords from a bio/description."""
    words = _normalize(text).split()
    # Filter out very short words and common stop words
    stop_words = {
        "the", "and", "for", "are", "but", "not", "you", "all",
        "can", "her", "was", "one", "our", "out", "has", "see",
        "from", "this", "that", "with", "have", "been", "more",
        "its", "also", "into", "will", "del", "las", "los", "una",
        "por", "con", "que", "para", "como", "est", "son",
    }
    return {w for w in words if len(w) >= min_len and w not in stop_words}


def _hash_image_url(url: str) -> str:
    """Create a stable hash of an image URL for comparison."""
    return hashlib.md5(url.encode()).hexdigest()[:12]


def _extract_name_from_email(
    email: str,
    *,
    known_usernames: list[str] | None = None,
) -> list[str]:
    """Extract probable name parts from an email address.

    If ``known_usernames`` is provided, the function tries to use them
    as a hint for splitting concatenated names.  E.g. knowing the
    username "xkissmely" helps split "kissmelymarcano" into
    "kissmely" + "marcano".

    Examples::

        kissmelymarcano@gmail.com  → ["kissmely", "marcano"]  (with hint)
        kissmely.marcano@gmail.com → ["kissmely", "marcano"]
        john_doe@gmail.com        → ["john", "doe"]
    """
    local_part = email.split("@")[0].lower()
    # Split by dots, underscores, hyphens first
    parts = re.split(r"[._\\-]+", local_part)
    if len(parts) >= 2:
        return [p for p in parts if len(p) >= 2]

    # Single word — try to split using known usernames as hints.
    word = parts[0]

    if known_usernames and len(word) >= 6:
        for uname in known_usernames:
            # Normalize: strip decorative prefixes/suffixes and trailing numbers
            uname = re.sub(r"^[xX_.\-]+", "", uname.lower())
            uname = re.sub(r"[\d_.\-]+$", "", uname)
            if len(uname) < 3:
                continue
            # Check if the username (or a variant) appears in the email
            idx = word.find(uname)
            if idx >= 0:
                end = idx + len(uname)
                # We found the name in the email; the rest is likely the surname
                name_part = word[idx:end]
                rest_before = word[:idx] if idx > 0 else ""
                rest_after = word[end:] if end < len(word) else ""
                result = []
                if rest_before and len(rest_before) >= 2:
                    result.append(rest_before)
                result.append(name_part)
                if rest_after and len(rest_after) >= 2:
                    result.append(rest_after)
                if len(result) >= 2:
                    return result

    # Fallback: try all possible split points
    if len(word) >= 6:
        best_split: list[str] = [word]
        best_balance = float("inf")
        for i in range(3, len(word) - 2):
            left, right = word[:i], word[i:]
            if len(left) >= 3 and len(right) >= 3:
                balance = abs(len(left) - len(right))
                if balance < best_balance:
                    best_balance = balance
                    best_split = [left, right]
        return best_split

    return parts


def build_reference_from_profiles(
    profiles: list[SocialProfile],
    anchors: list[TrustAnchor],
) -> ReferenceIdentity:
    """Build a reference identity from trusted profiles and anchors.

    Supports two anchor types:
    - **Network anchors** (``instagram:xkissmely``): match against
      scanned profiles to extract identity signals.
    - **Email anchors** (``email:kissmelymarcano@gmail.com``): extract
      name parts directly from the email address.
    """
    ref = ReferenceIdentity()

    # ── Process email anchors first (no profile match needed) ──
    # Collect usernames from non-email anchors to help split concatenated emails.
    known_usernames = [a.username for a in anchors if not a.is_email]

    for a in anchors:
        if a.is_email:
            ref.emails.add(a.username.lower())
            ref.trusted_networks["email"] = a.username
            # Extract name parts from email
            name_parts = _extract_name_from_email(
                a.username, known_usernames=known_usernames,
            )
            if name_parts:
                full_name = " ".join(name_parts)
                ref.names.add(full_name)
                logger.info(
                    "Email anchor '%s' → inferred name: '%s'",
                    a.username, full_name,
                )

    # ── Process network anchors against scanned profiles ──
    anchor_set = {
        (a.network, a.username.lower())
        for a in anchors
        if not a.is_email
    }

    for p in profiles:
        key = (p.network_name.lower(), p.username.lower())
        if key not in anchor_set:
            continue

        if not p.exists:
            continue

        ref.trusted_networks[p.network_name.lower()] = p.username

        # Extract name
        meta = p.metadata if isinstance(p.metadata, dict) else {}
        for name_field in ("name", "display_name", "og_title"):
            name = meta.get(name_field)
            if name and isinstance(name, str) and len(name.strip()) > 1:
                ref.names.add(_normalize(name))

        # Extract bio keywords
        if p.bio:
            ref.bio_keywords.update(_extract_keywords(p.bio))

        # Extract avatar hash
        if p.image_url:
            ref.avatar_hashes.add(_hash_image_url(p.image_url))

        # Extract email
        email = meta.get("email")
        if email and isinstance(email, str) and "@" in email:
            ref.emails.add(email.lower())

        # Extract location
        location = meta.get("location")
        if location and isinstance(location, str):
            ref.locations.add(_normalize(location))

    logger.info(
        "Built reference identity: %d names, %d keywords, %d avatar hashes, "
        "%d trusted networks, %d emails",
        len(ref.names), len(ref.bio_keywords), len(ref.avatar_hashes),
        len(ref.trusted_networks), len(ref.emails),
    )
    return ref


# ---------------------------------------------------------------------------
# Profile verification
# ---------------------------------------------------------------------------

@dataclass
class VerificationResult:
    """Result of comparing a profile against the reference."""
    verified: bool
    confidence: float  # 0.0 = definitely different, 1.0 = definitely same
    reasons: list[str] = field(default_factory=list)


def verify_profile(
    profile: SocialProfile,
    reference: ReferenceIdentity,
) -> VerificationResult:
    """Compare a profile against the reference identity.

    Returns a VerificationResult indicating whether the profile likely
    belongs to the same person.
    """
    if reference.is_empty():
        return VerificationResult(verified=True, confidence=0.5, reasons=["No reference data"])

    if not profile.exists:
        return VerificationResult(verified=True, confidence=1.0, reasons=["Profile does not exist"])

    # Trusted profiles are always verified.
    if profile.network_name.lower() in reference.trusted_networks:
        trusted_user = reference.trusted_networks[profile.network_name.lower()]
        if profile.username.lower() == trusted_user.lower():
            return VerificationResult(
                verified=True, confidence=1.0,
                reasons=["Trust anchor"],
            )

    score = 0.0
    max_score = 0.0
    reasons: list[str] = []

    meta = profile.metadata if isinstance(profile.metadata, dict) else {}

    # ── Name matching (weight: 40%) ──
    if reference.names:
        max_score += 40
        profile_name = None
        for name_field in ("name", "display_name", "og_title"):
            val = meta.get(name_field)
            if val and isinstance(val, str):
                profile_name = _normalize(val)
                break

        if profile_name:
            best_score = 0.0
            best_reason = "No name overlap"

            for ref_name in reference.names:
                # Exact match
                if profile_name == ref_name:
                    best_score = 40
                    best_reason = f"Name match: '{profile_name}'"
                    break

                name_words = set(profile_name.split())
                ref_words = set(ref_name.split())
                overlap = name_words & ref_words
                contradiction = name_words - ref_words

                # Check for NAME CONTRADICTION: if the profile has a
                # last name / word that does NOT appear in ANY reference
                # name, it's likely a different person.
                # e.g. reference="kissmely marcano", profile="kissmely almonte"
                #      → "almonte" contradicts → penalize heavily
                if overlap and contradiction:
                    # Has some matching words but also contradicting ones
                    # Check if contradicting words look like a different surname
                    all_ref_words: set[str] = set()
                    for rn in reference.names:
                        all_ref_words.update(rn.split())
                    hard_contradictions = {
                        w for w in contradiction
                        if len(w) >= 4 and w not in all_ref_words
                    }
                    if hard_contradictions:
                        # Name contradiction = likely different person
                        best_score = 0
                        best_reason = (
                            f"Name CONTRADICTION: profile has "
                            f"{hard_contradictions} not in reference "
                            f"{all_ref_words}"
                        )
                        break

                if overlap and len(overlap) >= 1:
                    partial = 20 + (20 * len(overlap) / max(len(ref_words), 1))
                    if partial > best_score:
                        best_score = partial
                        best_reason = f"Partial name match: {overlap}"

            score += min(40, best_score)
            reasons.append(best_reason)
        else:
            # No name data — neutral, don't penalize
            score += 20
            reasons.append("No name data to compare")

    # ── Bio keyword matching (weight: 30%) ──
    if reference.bio_keywords:
        max_score += 30
        if profile.bio:
            profile_keywords = _extract_keywords(profile.bio)
            overlap = profile_keywords & reference.bio_keywords
            if overlap:
                ratio = len(overlap) / max(len(reference.bio_keywords), 1)
                score += 30 * min(1.0, ratio * 2)  # Boost: 50% overlap = full score
                reasons.append(f"Bio keyword overlap: {len(overlap)}/{len(reference.bio_keywords)}")
            else:
                reasons.append("No bio keyword overlap")
        else:
            score += 15  # Neutral — no bio to compare
            reasons.append("No bio data to compare")

    # ── Avatar matching (weight: 20%) ──
    if reference.avatar_hashes:
        max_score += 20
        if profile.image_url:
            profile_hash = _hash_image_url(profile.image_url)
            if profile_hash in reference.avatar_hashes:
                score += 20
                reasons.append("Avatar URL match")
            else:
                reasons.append("Different avatar")
        else:
            score += 10
            reasons.append("No avatar to compare")

    # ── Location matching (weight: 10%) ──
    if reference.locations:
        max_score += 10
        location = meta.get("location")
        if location and isinstance(location, str):
            norm_loc = _normalize(location)
            for ref_loc in reference.locations:
                if ref_loc in norm_loc or norm_loc in ref_loc:
                    score += 10
                    reasons.append(f"Location match: '{location}'")
                    break
            else:
                reasons.append(f"Different location: '{location}'")
        else:
            score += 5
            reasons.append("No location to compare")

    confidence = score / max_score if max_score > 0 else 0.5
    # Threshold: profiles below 30% confidence are flagged
    verified = confidence >= 0.30

    return VerificationResult(
        verified=verified,
        confidence=round(confidence, 2),
        reasons=reasons,
    )


def filter_profiles_by_trust(
    profiles: list[SocialProfile],
    reference: ReferenceIdentity,
    *,
    remove: bool = False,
) -> list[SocialProfile]:
    """Filter/annotate profiles based on trust verification.

    Parameters
    ----------
    profiles:
        All scanned profiles.
    reference:
        Reference identity built from trust anchors.
    remove:
        If True, non-verified profiles with exists=True are set to
        exists=False.  If False, they are annotated but kept.

    Returns
    -------
    The (potentially modified) list of profiles.
    """
    if reference.is_empty():
        return profiles

    for p in profiles:
        if not p.exists:
            continue

        result = verify_profile(p, reference)

        # Annotate metadata
        if isinstance(p.metadata, dict):
            p.metadata["trust_verified"] = result.verified
            p.metadata["trust_confidence"] = result.confidence
            p.metadata["trust_reasons"] = result.reasons

        if not result.verified:
            logger.info(
                "Profile %s/%s flagged as false positive (confidence=%.2f): %s",
                p.network_name, p.username, result.confidence,
                "; ".join(result.reasons),
            )
            if remove:
                p.exists = False
                if isinstance(p.metadata, dict):
                    p.metadata["trust_discarded"] = True

    return profiles
