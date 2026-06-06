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
        """Parse ``network:username`` string.

        Examples::

            TrustAnchor.parse("instagram:xkissmely")
            TrustAnchor.parse("github:doble-2")
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
        return not self.names and not self.bio_keywords and not self.avatar_hashes


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


def build_reference_from_profiles(
    profiles: list[SocialProfile],
    anchors: list[TrustAnchor],
) -> ReferenceIdentity:
    """Build a reference identity from trusted profiles.

    Only profiles that match a declared trust anchor contribute to the
    reference.
    """
    ref = ReferenceIdentity()

    anchor_set = {(a.network, a.username.lower()) for a in anchors}

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
        "%d trusted networks",
        len(ref.names), len(ref.bio_keywords), len(ref.avatar_hashes),
        len(ref.trusted_networks),
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
            # Check for any overlap
            for ref_name in reference.names:
                # Exact match
                if profile_name == ref_name:
                    score += 40
                    reasons.append(f"Name match: '{profile_name}'")
                    break
                # Partial match (shared words)
                name_words = set(profile_name.split())
                ref_words = set(ref_name.split())
                overlap = name_words & ref_words
                if overlap and len(overlap) >= 1:
                    partial = 20 + (20 * len(overlap) / max(len(ref_words), 1))
                    score += min(40, partial)
                    reasons.append(f"Partial name match: {overlap}")
                    break
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
