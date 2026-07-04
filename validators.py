"""
Lightweight AI Quality Checks from the spec (character limits, CTA presence,
hashtag counts, basic sanity checks). This is NOT a grammar checker -- it's a
fast pre-return sanity pass. Plug a real grammar API in later if needed.
"""

from typing import Dict, List

from models import Platform
from config import PLATFORM_RULES


def run_quality_checks(platform: Platform, content: dict) -> List[str]:
    """Returns a list of warning strings. Empty list = passed all checks."""
    warnings: List[str] = []
    rules = PLATFORM_RULES[platform]

    post = content.get("social_post", "")
    if post:
        target = rules["post_char_target"]
        if len(post) > target * 1.4:
            warnings.append(
                f"Social post is {len(post)} chars, notably longer than the "
                f"~{target} char target for {platform.value}."
            )

    cta = content.get("cta", "")
    if not cta or not cta.strip():
        warnings.append("CTA is missing or empty.")

    hashtags = content.get("hashtags", [])
    expected = rules["hashtag_count"]
    if hashtags and abs(len(hashtags) - expected) > 3:
        warnings.append(
            f"Hashtag count ({len(hashtags)}) is far from the "
            f"{platform.value} target of ~{expected}."
        )
    if any(not h.startswith("#") for h in hashtags):
        warnings.append("One or more hashtags is missing the '#' prefix.")

    headlines = content.get("headlines", {})
    if not headlines.get("primary"):
        warnings.append("Primary headline is missing.")

    image_text = content.get("image_text", {})
    if image_text:
        headline = image_text.get("headline", "")
        if len(headline.split()) > 7:
            warnings.append("Image overlay headline is too long to read at a glance.")

    return warnings
