# Trust Anchor System

OSINT-D2's Trust Anchor system solves a fundamental problem in OSINT: **false positives**. When you scan the username `chad` across 30+ platforms, multiple different people share that handle. Trust anchors let you declare which profiles are *known* to belong to your target, and the system automatically filters the rest.

!!! example "The problem"
    Scanning `torvalds` finds profiles on GitHub (Linus Torvalds), Pinterest (Marco Migozzi), Kaggle (Pengze Lin), and Telegram (unknown). Without trust anchors, the agent might conflate all of them into one person.

---

## How It Works

### 1. Declare Anchors

Pass known-good identifiers with the `--trust` flag:

```bash
osint-d2 agent -u torvalds --trust github:torvalds,email:torvalds@linux-foundation.org
```

Supported anchor types:

| Type | Format | Example |
|------|--------|---------|
| Network | `network:username` | `github:torvalds`, `instagram:xkissmely` |
| Email | `email:address` | `email:john@example.com` |

Multiple anchors can be combined. Their signals are **merged** into a single reference identity.

### 2. Build Reference Identity

The system scans trusted profiles first and extracts **identity signals**:

```
TrustAnchor("github", "torvalds")
    → Scan github.com/torvalds
    → Extract: name="Linus Torvalds", location="Portland, OR"
    → Extract: bio keywords = ["linux", "kernel", "git"]
    → Extract: avatar hash = md5(avatar_url)[:12]

TrustAnchor("email", "torvalds@linux-foundation.org")
    → Split email: "torvalds" (already known from username)
    → Add to reference emails
```

Email anchors use a **heuristic name splitter** that can decompose concatenated addresses:

| Email | Extracted Name |
|-------|---------------|
| `kissmely.marcano@gmail.com` | kissmely marcano |
| `john_doe@gmail.com` | john doe |
| `kissmelymarcano@gmail.com` | kissmely marcano *(with username hint `xkissmely`)* |

When known usernames are provided (from non-email anchors), the splitter uses them as hints. For example, knowing the username `xkissmely` helps split `kissmelymarcano` into `kissmely` + `marcano` by finding the username substring within the email.

### 3. Verify Profiles

After scanning all networks, each discovered profile is compared against the reference using **4-signal weighted scoring**:

| Signal | Weight | What it checks |
|--------|--------|---------------|
| **Name** | 40% | Display name vs reference names. Exact match = 40pts. Partial overlap = 20-40pts. |
| **Bio keywords** | 30% | Keyword overlap between profile bio and trusted bios. 50%+ overlap = full score. |
| **Avatar** | 20% | MD5 hash of image URL matches any reference avatar hash. |
| **Location** | 10% | Substring match against reference locations. |

**Confidence threshold**: profiles below **30% confidence** are flagged as false positives.

### 4. Name Contradiction Detection

The most powerful signal is **name contradiction**. If the reference identity establishes the target as "Kissmely Marcano" and a profile shows "Kissmely Almonte", the different surname triggers a hard contradiction — the profile is almost certainly a different person.

```
Reference names: {"kissmely marcano"}
Profile name:    "kissmely almonte"
    → Overlap: {"kissmely"} ✓
    → Contradiction: {"almonte"} ✗ (not in any reference name)
    → Hard contradiction (len("almonte") >= 4) → score = 0
    → Verdict: FALSE POSITIVE
```

This prevents the agent from merging different people who happen to share a first name or common handle.

---

## Visual Example

<div class="os-screenshot" markdown>

![Trust Anchors Filtering](../assets/trust_anchors.png)
<div class="os-screenshot__caption">Trust anchors discarded 2 false positive(s) from a scan of "torvalds"</div>

</div>

The screenshot shows a scan where `github:torvalds` was declared as a trust anchor. After scanning 18+ platforms, the system verified each profile against the reference built from GitHub and **automatically discarded** profiles belonging to different people.

---

## In Agent Mode

When trust anchors are provided to Agent Mode, the system prompt is augmented with a `TRUSTED SOURCES` block:

```
TRUSTED SOURCES (user-verified data):
- VERIFIED GITHUB account: @torvalds
- VERIFIED EMAIL: torvalds@linux-foundation.org

IMPORTANT: Use these as ground truth. If a profile on another
network has a different name/surname than what these sources
suggest, that profile likely belongs to a DIFFERENT PERSON.
Do NOT conflate identities.
```

This context is injected into the LLM's conversation, ensuring the AI agent respects the ground truth throughout its investigation.

---

## Configuration

Trust anchors work in all modes:

```bash
# Agent mode
osint-d2 agent -u target --trust github:user,email:user@domain.com

# Interactive CLI (prompted)
osint-d2
# → "Add trusted identity sources?" [y/n]: y
# → Trust anchor(s) (): github:torvalds

# Web dashboard
# → Configure trust anchors in the sidebar before starting
```

!!! tip "Best practice"
    Start with the platform where you're most confident about the target's identity. GitHub profiles with real names and locations make excellent anchors because they provide all 4 signals (name, bio, avatar, location).
