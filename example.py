"""
Quick manual test -- run this directly in PyCharm to sanity-check the pipeline.

    python example.py

Make sure OPENAI_API_KEY is set in your environment (or a .env file, see
.env.example) before running.
"""

import json
import os

from dotenv import load_dotenv

from models import (
    CampaignGoal,
    ContentTone,
    Platform,
    ContentType,
    CampaignInput,
    OptionalBrandInputs,
)
from generator import MarketingContentGenerator

load_dotenv()  # pulls OPENAI_API_KEY from a local .env file if present


def main():
    # This mirrors the HVAC example from the UI mockups.
    campaign = CampaignInput(
        campaign_goal=CampaignGoal.DRIVE_AWARENESS,
        content_tone=ContentTone.PROFESSIONAL,
        target_audience="Homeowners aged 30-55 in suburban areas",
        target_platforms=[Platform.FACEBOOK],
        key_message="Highlight our fall HVAC tune-up offer with limited-time pricing.",
        optional=OptionalBrandInputs(
            industry="Home Services / HVAC",
            location="Suburban US",
        ),
    )

    generator = MarketingContentGenerator()

    result = generator.generate(
        campaign=campaign,
        content_types=[ContentType.COMPLETE_PACKAGE],
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
