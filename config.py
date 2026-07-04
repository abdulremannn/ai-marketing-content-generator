"""
Static config the prompt builder and validators pull from.
This is where "platform intelligence" and "goal strategy" from the spec live.
Tune these numbers/notes as you learn what performs well.
"""

from models import CampaignGoal, Platform

# ---- Platform intelligence -------------------------------------------------
# Character limits are soft targets for good UX/engagement, not hard API limits.
PLATFORM_RULES = {
    Platform.LINKEDIN: {
        "style": "Professional, business language, thought-leadership tone.",
        "post_char_target": 700,
        "hashtag_count": 3,
        "hashtag_style": "Industry-specific tags",
        "emoji_usage": "minimal",
        "cta_style": "Direct but professional (e.g. 'Learn more', 'Book a demo')",
        "image_aspect_ratio": "1:1 or 4:5",  # fallback if no format selected
    },
    Platform.FACEBOOK: {
        "style": "Conversational, community-focused, storytelling.",
        "post_char_target": 400,
        "hashtag_count": 2,
        "hashtag_style": "Broad, general-engagement tags",
        "emoji_usage": "moderate",
        "cta_style": "Friendly, inviting (e.g. 'Check it out', 'Shop today')",
        "image_aspect_ratio": "1:1 or 4:5",
    },
    Platform.INSTAGRAM: {
        "style": "Visual, lifestyle-driven, short and emotion-first captions.",
        "post_char_target": 200,
        "hashtag_count": 8,
        "hashtag_style": "Discoverability-focused, mix of broad + niche tags",
        "emoji_usage": "high",
        "cta_style": "Short, punchy (e.g. 'Tap to shop', 'Link in bio')",
        "image_aspect_ratio": "4:5 or 1:1",
    },
    Platform.TWITTER: {
        "style": "Very concise, high-impact, direct.",
        "post_char_target": 240,
        "hashtag_count": 2,
        "hashtag_style": "Trending-style, short tags",
        "emoji_usage": "low-moderate",
        "cta_style": "Punchy, urgent",
        "image_aspect_ratio": "16:9",
    },
}

# ---- Platform FORMATS (new) -------------------------------------------------
# Each platform supports multiple real placement types, each with its own
# aspect ratio + orientation + how much that squeezes/loosens text length.
# UI: user picks one format per platform (defaults to the first in the list).
# This feeds both build_image_generation_prompt (aspect ratio) and
# build_text_prompt (char target + orientation-aware copy instructions).
PLATFORM_FORMATS = {
    Platform.LINKEDIN: [
        {
            "id": "feed_square",
            "label": "Feed Post (Square)",
            "aspect_ratio": "1:1",
            "orientation": "square",
            "char_multiplier": 1.0,
        },
        {
            "id": "feed_landscape",
            "label": "Feed Post (Landscape)",
            "aspect_ratio": "1.91:1",
            "orientation": "landscape",
            "char_multiplier": 1.1,
        },
    ],
    Platform.FACEBOOK: [
        {
            "id": "feed_square",
            "label": "Feed Post (Square)",
            "aspect_ratio": "1:1",
            "orientation": "square",
            "char_multiplier": 1.0,
        },
        {
            "id": "story",
            "label": "Story",
            "aspect_ratio": "9:16",
            "orientation": "vertical",
            "char_multiplier": 0.5,
        },
    ],
    Platform.INSTAGRAM: [
        {
            "id": "feed_portrait",
            "label": "Feed Post (Portrait)",
            "aspect_ratio": "4:5",
            "orientation": "portrait",
            "char_multiplier": 1.0,
        },
        {
            "id": "story",
            "label": "Story / Reel Cover",
            "aspect_ratio": "9:16",
            "orientation": "vertical",
            "char_multiplier": 0.4,
        },
        {
            "id": "feed_square",
            "label": "Feed Post (Square)",
            "aspect_ratio": "1:1",
            "orientation": "square",
            "char_multiplier": 1.0,
        },
    ],
    Platform.TWITTER: [
        {
            "id": "feed_landscape",
            "label": "In-Feed Image",
            "aspect_ratio": "16:9",
            "orientation": "landscape",
            "char_multiplier": 1.0,
        },
    ],
}


def get_platform_format(platform: Platform, format_id: str = None) -> dict:
    """
    Looks up the chosen format for a platform, falling back to the
    first (default) format if none/invalid was selected.
    """
    formats = PLATFORM_FORMATS[platform]
    if format_id:
        for f in formats:
            if f["id"] == format_id:
                return f
    return formats[0]


# ---- Goal -> marketing strategy / framework --------------------------------
GOAL_STRATEGY = {
    CampaignGoal.DRIVE_AWARENESS: {
        "focus": "Brand recognition, reach, education.",
        "preferred_frameworks": ["Storytelling", "Emotional Marketing", "Authority"],
    },
    CampaignGoal.BOOST_ENGAGEMENT: {
        "focus": "Conversation, shares, comments, community participation.",
        "preferred_frameworks": ["Storytelling", "Social Proof", "Emotional Marketing"],
    },
    CampaignGoal.RETAIN_CUSTOMERS: {
        "focus": "Loyalty, ongoing value, relationship reinforcement.",
        "preferred_frameworks": ["Before-After-Bridge", "Social Proof", "Benefit-Driven Messaging"],
    },
    CampaignGoal.INCREASE_CONVERSIONS: {
        "focus": "Offers, urgency, sales, strong CTA.",
        "preferred_frameworks": ["AIDA", "PAS", "Scarcity", "Loss Aversion"],
    },
}

# ---- Tone guidance (short style anchors, not exhaustive) -------------------
TONE_NOTES = {
    "Professional": "Polished, credible, industry-appropriate vocabulary.",
    "Friendly": "Warm, approachable, conversational, second-person.",
    "Bold": "Confident, punchy, a little provocative, short sentences.",
    "Inspirational": "Uplifting, big-picture, aspirational language.",
    "Playful": "Light, fun, casual, can use humor and emoji.",
    "Urgent": "Time-sensitive language, scarcity, direct calls to act now.",
}

# ---- Image generation defaults ---------------------------------------------
IMAGE_MODEL_DEFAULT = "gpt-image-1"  # swap for "dall-e-3" if you prefer/need it
IMAGE_SIZE_DEFAULT = "1024x1024"

# Real pixel size sent to the API per orientation, so output actually
# matches the format picked in the UI (not just described in the prompt).
ORIENTATION_TO_IMAGE_SIZE = {
    "square": "1024x1024",
    "portrait": "1024x1536",
    "vertical": "1024x1536",
    "landscape": "1536x1024",
}

TEXT_MODEL_DEFAULT = "gpt-4o"