"""Fuentes OSINT (scanners concretos).

Por qué un paquete:
- Agrupa módulos por fuente (GitHub, Sherlock-like, etc.).
- Cada módulo implementará `core.interfaces.scanner.OSINTScanner`.
"""

from adapters.osint_sources.aboutme import AboutMeScanner
from adapters.osint_sources.behance import BehanceScanner
from adapters.osint_sources.devto import DevToScanner
from adapters.osint_sources.dribbble import DribbbleScanner
from adapters.osint_sources.gist_github import GitHubGistScanner
from adapters.osint_sources.github import GitHubScanner
from adapters.osint_sources.gitlab import GitLabScanner
from adapters.osint_sources.kaggle import KaggleScanner
from adapters.osint_sources.keybase import KeybaseScanner
from adapters.osint_sources.medium import MediumScanner
from adapters.osint_sources.npm import NpmScanner
from adapters.osint_sources.pinterest import PinterestScanner
from adapters.osint_sources.producthunt import ProductHuntScanner
from adapters.osint_sources.reddit import RedditScanner
from adapters.osint_sources.soundcloud import SoundCloudScanner
from adapters.osint_sources.telegram import TelegramScanner
from adapters.osint_sources.twitch import TwitchScanner
from adapters.osint_sources.x import XScanner

__all__ = [
	"AboutMeScanner",
	"BehanceScanner",
	"DevToScanner",
	"DribbbleScanner",
	"GitHubScanner",
	"GitHubGistScanner",
	"GitLabScanner",
	"KaggleScanner",
	"KeybaseScanner",
	"MediumScanner",
	"NpmScanner",
	"PinterestScanner",
	"ProductHuntScanner",
	"RedditScanner",
	"SoundCloudScanner",
	"TelegramScanner",
	"TwitchScanner",
	"XScanner",
]
