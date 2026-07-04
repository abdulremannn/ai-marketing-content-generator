"""
Main entry point: MarketingContentGenerator.

Usage:
    gen = MarketingContentGenerator()
    result = gen.generate(campaign_input, content_types=[ContentType.COMPLETE_PACKAGE])

Returns a dict keyed by platform, each containing the requested content
plus a "warnings" list from the quality checks.
"""

import base64
import json
import os
import uuid
from typing import Dict, List, Optional

from openai import OpenAI

from models import CampaignInput, ContentType, Platform
from prompt_builder import (
    build_text_prompt,
    build_image_generation_prompt,
    build_headline_regen_prompt,
    build_caption_regen_prompt,
    build_image_revision_prompt,
)
from validators import run_quality_checks
from config import (
    PLATFORM_RULES,
    TEXT_MODEL_DEFAULT,
    IMAGE_MODEL_DEFAULT,
    IMAGE_SIZE_DEFAULT,
    ORIENTATION_TO_IMAGE_SIZE,
    get_platform_format,
)


class MarketingContentGenerator:
    def __init__(
        self,
        api_key: Optional[str] = None,
        text_model: str = TEXT_MODEL_DEFAULT,
        image_model: str = IMAGE_MODEL_DEFAULT,
        image_size: str = IMAGE_SIZE_DEFAULT,
    ):
        # Falls back to OPENAI_API_KEY env var if not passed explicitly.
        self.client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
        self.text_model = text_model
        self.image_model = image_model
        self.image_size = image_size

    # -- public API -----------------------------------------------------

    def generate(
        self,
        campaign: CampaignInput,
        content_types: List[ContentType],
        images_output_dir: str = "generated_images",
    ) -> Dict[str, dict]:
        """
        Runs generation for every platform selected in the campaign.
        Returns: { "LinkedIn": {...}, "Facebook": {...}, ... }
        """
        wants_image = (
            ContentType.AI_IMAGE in content_types
            or ContentType.COMPLETE_PACKAGE in content_types
        )

        results: Dict[str, dict] = {}
        for platform in campaign.target_platforms:
            text_content = self._generate_text(campaign, platform)
            filtered = self._filter_by_content_type(text_content, content_types)

            if wants_image and "image_prompt" in text_content:
                image_path, final_image_prompt = self._generate_image(
                    text_content["image_prompt"],
                    platform,
                    images_output_dir,
                    format_id=campaign.platform_formats.get(platform),
                )
                filtered["image_path"] = image_path
                filtered["final_image_prompt"] = final_image_prompt
                filtered["raw_image_prompt"] = text_content["image_prompt"]

            filtered["warnings"] = run_quality_checks(platform, text_content)
            results[platform.value] = filtered

        return results

    def regenerate_headlines(
        self,
        campaign: CampaignInput,
        platform: Platform,
        previous_headlines: List[str],
    ) -> dict:
        """
        Regenerate button: produces a fresh {primary, alternatives} pair
        that avoids repeating previous_headlines. Cheap/fast — headline-only
        prompt, no social_post/image regeneration.
        """
        system_prompt, user_prompt = build_headline_regen_prompt(campaign, platform, previous_headlines)
        response = self.client.chat.completions.create(
            model=self.text_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.9,
        )
        raw = response.choices[0].message.content
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Model did not return valid JSON for headline regen. Raw:\n{raw}") from e

    def regenerate_caption(
        self,
        campaign: CampaignInput,
        platform: Platform,
        previous_caption: str,
    ) -> str:
        """Regenerate button for the caption/social_post text."""
        system_prompt, user_prompt = build_caption_regen_prompt(campaign, platform, previous_caption)
        response = self.client.chat.completions.create(
            model=self.text_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.9,
        )
        raw = response.choices[0].message.content
        try:
            return json.loads(raw)["social_post"]
        except (json.JSONDecodeError, KeyError) as e:
            raise RuntimeError(f"Model did not return valid JSON for caption regen. Raw:\n{raw}") from e

    def regenerate_image(
        self,
        campaign: CampaignInput,
        platform: Platform,
        previous_image_prompt: str,
        user_feedback: str,
        images_output_dir: str = "generated_images",
    ) -> tuple[str, str, str]:
        """
        "I don't like the image" flow. Revises the raw scene prompt using the
        user's feedback, then re-runs actual image generation with it.
        Returns (image_path, final_image_prompt, revised_raw_prompt).
        """
        system_prompt, user_prompt = build_image_revision_prompt(
            campaign, platform, previous_image_prompt, user_feedback
        )
        response = self.client.chat.completions.create(
            model=self.text_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.8,
        )
        raw = response.choices[0].message.content
        try:
            revised_prompt = json.loads(raw)["image_prompt"]
        except (json.JSONDecodeError, KeyError) as e:
            raise RuntimeError(f"Model did not return valid JSON for image revision. Raw:\n{raw}") from e

        image_path, final_image_prompt = self._generate_image(
            revised_prompt,
            platform,
            images_output_dir,
            format_id=campaign.platform_formats.get(platform),
        )
        return image_path, final_image_prompt, revised_prompt

    # -- internals --------------------------------------------------------

    def _generate_text(self, campaign: CampaignInput, platform: Platform) -> dict:
        system_prompt, user_prompt = build_text_prompt(campaign, platform)

        response = self.client.chat.completions.create(
            model=self.text_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.8,
        )

        raw = response.choices[0].message.content
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Model did not return valid JSON for {platform.value}. Raw output:\n{raw}"
            ) from e

    def _generate_image(
        self, image_prompt_text: str, platform: Platform, output_dir: str, format_id: str = None
    ) -> tuple[str, str]:
        # Uses the selected format's aspect ratio (e.g. Story = 9:16)
        # instead of the platform's generic default.
        fmt = get_platform_format(platform, format_id)
        final_prompt = build_image_generation_prompt(image_prompt_text, fmt["aspect_ratio"])
        # Real pixel size matching the orientation, not just described in text.
        actual_size = ORIENTATION_TO_IMAGE_SIZE.get(fmt["orientation"], self.image_size)

        response = self.client.images.generate(
            model=self.image_model,
            prompt=final_prompt,
            size=actual_size,
            n=1,
        )

        os.makedirs(output_dir, exist_ok=True)
        safe_platform = platform.value.lower().replace(" ", "_")
        safe_format = fmt["id"]
        unique_suffix = uuid.uuid4().hex[:8]
        out_path = os.path.join(output_dir, f"{safe_platform}_{safe_format}_{unique_suffix}.png")

        data = response.data[0]
        if getattr(data, "b64_json", None):
            image_bytes = base64.b64decode(data.b64_json)
            with open(out_path, "wb") as f:
                f.write(image_bytes)
        elif getattr(data, "url", None):
            # dall-e-3 style response: download it.
            import urllib.request
            urllib.request.urlretrieve(data.url, out_path)
        else:
            raise RuntimeError("Image response contained neither b64_json nor url.")

        return out_path, final_prompt

    @staticmethod
    def _filter_by_content_type(full_content: dict, content_types: List[ContentType]) -> dict:
        if ContentType.COMPLETE_PACKAGE in content_types:
            return dict(full_content)  # everything

        wanted = {}
        if ContentType.HEADLINES in content_types and "headlines" in full_content:
            wanted["headlines"] = full_content["headlines"]
        if ContentType.SOCIAL_POST in content_types and "social_post" in full_content:
            wanted["social_post"] = full_content["social_post"]
        if ContentType.CTA in content_types and "cta" in full_content:
            wanted["cta"] = full_content["cta"]
        if ContentType.HASHTAGS in content_types and "hashtags" in full_content:
            wanted["hashtags"] = full_content["hashtags"]
        if ContentType.IMAGE_TEXT in content_types and "image_text" in full_content:
            wanted["image_text"] = full_content["image_text"]
        if ContentType.AI_IMAGE in content_types and "image_prompt" in full_content:
            wanted["image_prompt"] = full_content["image_prompt"]
        return wanted