"""
Core data models for the AI Marketing Content Generator.
These mirror the Step 1 / Step 2 UI fields from the spec.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class CampaignGoal(str, Enum):
    DRIVE_AWARENESS = "Drive Awareness"
    BOOST_ENGAGEMENT = "Boost Engagement"
    RETAIN_CUSTOMERS = "Retain Customers"
    INCREASE_CONVERSIONS = "Increase Conversions"


class ContentTone(str, Enum):
    PROFESSIONAL = "Professional"
    FRIENDLY = "Friendly"
    BOLD = "Bold"
    INSPIRATIONAL = "Inspirational"
    PLAYFUL = "Playful"
    URGENT = "Urgent"


class Platform(str, Enum):
    LINKEDIN = "LinkedIn"
    FACEBOOK = "Facebook"
    INSTAGRAM = "Instagram"
    TWITTER = "X"
    # TikTok / Threads are marked "future" in the spec — left out until designed.


class ContentType(str, Enum):
    HEADLINES = "Headlines"
    SOCIAL_POST = "Social Posts"
    AI_IMAGE = "AI Image"
    IMAGE_TEXT = "Image Text"
    CTA = "Call To Action"
    HASHTAGS = "Hashtags"
    COMPLETE_PACKAGE = "Complete Package"


@dataclass
class OptionalBrandInputs:
    """Step-later optional inputs from the spec. All optional."""
    company_name: Optional[str] = None
    brand_colors: Optional[List[str]] = None
    website_url: Optional[str] = None
    industry: Optional[str] = None
    location: Optional[str] = None
    target_gender: Optional[str] = None
    age_range: Optional[str] = None
    image_style: Optional[str] = None  # Photography, 3D Render, Illustration, Flat, Luxury, Minimal, Corporate, Modern, Retro


@dataclass
class CampaignInput:
    """Everything the user fills in on Step 1 of the UI."""
    campaign_goal: CampaignGoal
    content_tone: ContentTone
    target_audience: str
    target_platforms: List[Platform]
    key_message: str
    optional: OptionalBrandInputs = field(default_factory=OptionalBrandInputs)
    # NEW: per-platform chosen format (e.g. Instagram -> "story").
    # If a platform isn't in this dict, config.get_platform_format() falls
    # back to that platform's default (first) format.
    platform_formats: Dict[Platform, str] = field(default_factory=dict)
    # NEW: if True, the AI bakes marketing text (headline/CTA) into the image
    # itself. If False, image stays clean/text-free (overlay done elsewhere).
    text_on_image: bool = False

    def __post_init__(self):
        if not self.target_platforms:
            raise ValueError("At least one target platform must be selected.")
        if not self.key_message.strip():
            raise ValueError("Key message cannot be empty.")
        if not self.target_audience.strip():
            raise ValueError("Target audience cannot be empty.")