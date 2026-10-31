# Trust Anchor System

Different people often share a handle. Trust anchors let you declare which accounts are known to belong to your target, so OSINT-D2 can discard profiles that contradict them.

!!! example "The problem"
    Scanning `johndoe` finds a GitHub profile for John Doe, a Pinterest profile for Marco Bianchi, and a Kaggle profile for Li Wei (all fictitious). Without anchors, an agent might merge them into one person.

---

## How It Works

### 1. Declare anchors

```bash
osint-d2 agent johndoe --trust github:johndoe --trust email:john@example.com
```

| Type | Format | Example |
|------|--------|---------|
| Network | `network:username` | `github:johndoe` |
| Email | `email:address` | `email:john@example.com` |

Signals from several anchors are merged into a single reference identity.

### 2. Build the reference identity

```
TrustAnchor("github", "johndoe")
    → Find the scanned profile for github.com/johndoe
    → Extract: name="John Doe", location="Lisbon"
    → Extract: bio keywords = ["python", "security"]
    → Extract: avatar hash = md5(avatar_url)[:12]

TrustAnchor("email", "john@example.com")
    → Split the local part into a name, if possible
    → Add to reference emails
```

Email anchors use a heuristic name splitter:

| Email | Extracted name |
|-------|---------------|
| `janelle.rivera@example.com` | janelle rivera |
| `john_doe@example.com` | john doe |
| `janellerivera@example.com` | janelle rivera *(with the username hint `xjanelle`)* |

Known usernames from other anchors serve as hints: finding `janelle` inside `janellerivera` splits it into two names.

### 3. Verify profiles

Each discovered profile is compared with the reference using weighted signals:

| Signal | Weight | What it checks |
|--------|--------|---------------|
| **Name** | 40% | Display name vs. reference names. Exact match = 40 points, partial overlap = 20–40. |
| **Bio keywords** | 30% | Keyword overlap with trusted bios. 50%+ overlap = full score. |
| **Avatar** | 20% | MD5 of the image URL matches a reference avatar hash. |
| **Location** | 10% | Substring match against reference locations. |

Profiles below **30% confidence** are flagged as false positives.

### 4. Detect name contradictions

A different surname is a hard contradiction, because it usually means a different person:

```
Reference names: {"janelle rivera"}
Profile name:    "janelle castro"
    → Overlap: {"janelle"} ✓
    → Contradiction: {"castro"} ✗ (not in any reference name)
    → Hard contradiction (len("castro") >= 4) → score = 0
    → Verdict: FALSE POSITIVE
```

---

## In Agent Mode

The agent's first message includes a `TRUSTED SOURCES` block:

```
TRUSTED SOURCES (user-verified data):
- VERIFIED GITHUB account: @johndoe
- VERIFIED EMAIL: john@example.com

IMPORTANT: Use these as ground truth. If a profile on another
network has a different name/surname than what these sources
suggest, that profile likely belongs to a DIFFERENT PERSON.
Do NOT conflate identities.
```

---

## Where to Use Them

```bash
# Agent mode
osint-d2 agent johndoe --trust github:johndoe --trust email:john@example.com

# Direct scans
osint-d2 scan johndoe --trust github:johndoe
osint-d2 hunt -u johndoe --trust github:johndoe

# Interactive wizard: answer yes to "Add trusted identity sources?"
osint-d2 wizard
```

In the [dashboard](../guides/web-dashboard.md), enter them under **Verified accounts**.

!!! tip "Best practice"
    Start with the platform where you're most confident about the identity. Profiles with a real name, bio, avatar, and location provide all four signals.

!!! note "This is a heuristic"
    A wrong anchor makes every later decision wrong, and a true match can be discarded if someone uses different names across platforms. Review what was discarded.
