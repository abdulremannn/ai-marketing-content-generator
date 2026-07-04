"""
Turns a CampaignInput into the actual prompts sent to the LLM.
This is the "brain" that encodes platform intelligence, goal strategy,
tone, and marketing frameworks -- the user never sees this reasoning.

Below, every UI field is annotated with EXACTLY what it adds to the
final prompt, since that logic isn't visible anywhere else.
"""

import json
from typing import List

from models import CampaignInput, ContentType, Platform
from config import PLATFORM_RULES, GOAL_STRATEGY, TONE_NOTES, get_platform_format


# Full output schema the model always fills in. We filter down to what the
# user actually asked for after parsing -- simpler and more reliable than
# trying to dynamically reshape the JSON schema per request.
OUTPUT_SCHEMA_DESCRIPTION = {
    "headlines": {
        "primary": "string - the strongest headline",
        "alternatives": "array of 2-4 alternative headlines",
    },
    "social_post": "string - the full platform-ready caption/post copy",
    "cta": "string - a single strong call to action phrase",
    "hashtags": "array of strings, each starting with #",
    "image_prompt": "string - a single, extremely detailed prompt for an AI image generator. "
                     "Do NOT just restate the key message. ENHANCE it into a full scene, and "
                     "explicitly cover EVERY one of these categories (in prose, not a list), "
                     "each one derived from the specific campaign inputs below rather than "
                     "generic filler:\n"
                     "1. Subject definition -- exact main subject, built from KEY MESSAGE + "
                     "CAMPAIGN GOAL.\n"
                     "2. Scene description -- the environment in detail.\n"
                     "3. Environment context -- location and atmosphere, built from INDUSTRY/"
                     "LOCATION if provided, otherwise inferred from TARGET AUDIENCE.\n"
                     "4. Object specification -- concrete props/objects relevant to the "
                     "KEY MESSAGE.\n"
                     "5. Composition -- framing, camera angle, subject placement, matching the "
                     "PLATFORM/FORMAT orientation.\n"
                     "6. Lighting -- source, direction, intensity, mood, matching CONTENT TONE.\n"
                     "7. Camera settings -- camera model/lens/aperture/photographic character.\n"
                     "8. Depth of field -- focus plane and background blur behavior.\n"
                     "9. Material realism -- realistic textures/surfaces for everything shown.\n"
                     "10. Color palette -- built from BRAND COLORS if provided, otherwise a "
                     "palette that fits CONTENT TONE and industry.\n"
                     "11. Reflections and shadows -- physically accurate light behavior.\n"
                     "12. Image quality -- resolution/realism expectation.\n"
                     "13. Style -- visual/artistic direction consistent with CONTENT TONE and "
                     "PREFERRED IMAGE STYLE if provided.\n"
                     "14. Brand integration -- naturally work in COMPANY NAME/brand cues if "
                     "provided, without looking like a sticker.\n"
                     "15. Technical interface detail -- if any screen/device/UI appears, "
                     "describe realistic on-screen content, not blank/placeholder screens.\n"
                     "16. Atmosphere -- emotional/professional tone matching CAMPAIGN GOAL + "
                     "CONTENT TONE.\n"
                     "17. Real-world imperfections -- pores, dust, hair strands, fabric "
                     "wrinkles, natural asymmetry -- so it doesn't look synthetic.\n"
                     "18. Negative constraints -- explicitly state what to avoid for this "
                     "specific scene (beyond the global negative prompt added later).\n"
                     "19. Consistency -- every element (people, objects, lighting, style) "
                     "supports one coherent visual identity, not mixed styles.\n"
                     "20. Photographic authenticity -- explicit instruction that the result "
                     "must be indistinguishable from a real photograph, not a rendering.\n"
                     "Also include aspect ratio, and if TEXT_ON_IMAGE is on, the exact overlay "
                     "text and where it sits; if off, explicitly say clean/no text, reserve "
                     "negative space instead.",
    "image_text": {
        "headline": "string - short punchy line to overlay on the image (max ~5 words)",
        "supporting": "string - short supporting line (max ~8 words)",
        "cta": "string - short CTA for the image overlay (max ~4 words)",
    },
}


def _platform_block(platform: Platform, format_id: str = None) -> str:
    """
    PROMPT EFFECT — TARGET PLATFORM + FORMAT selection:
    Adds a "Platform:" block to the user_prompt with style, char target,
    hashtag rules, emoji usage, CTA style, and aspect ratio.

    NEW: format_id (e.g. "story" vs "feed_square") changes two things:
      1. post_char_target is multiplied by that format's char_multiplier
         (e.g. Instagram Story = 0.4x -> forces much shorter, punchier copy
         since Stories are glanced at, not read).
      2. image_aspect_ratio is overridden by the format's own aspect_ratio
         instead of the platform's generic default, and orientation
         (square/vertical/landscape) is explicitly told to the model so
         image_prompt composition (e.g. negative space placement) matches.
    """
    rules = PLATFORM_RULES[platform]
    fmt = get_platform_format(platform, format_id)
    adjusted_char_target = int(rules["post_char_target"] * fmt["char_multiplier"])

    return (
        f"Platform: {platform.value}\n"
        f"- Format: {fmt['label']} ({fmt['orientation']})\n"
        f"- Style: {rules['style']}\n"
        f"- Target post length: ~{adjusted_char_target} characters "
        f"(adjusted for {fmt['label']} format)\n"
        f"- Hashtags: {rules['hashtag_count']} tags, {rules['hashtag_style']}\n"
        f"- Emoji usage: {rules['emoji_usage']}\n"
        f"- CTA style: {rules['cta_style']}\n"
        f"- Image aspect ratio: {fmt['aspect_ratio']}\n"
        f"- Orientation-specific note: {_orientation_note(fmt['orientation'])}\n"
    )


def _orientation_note(orientation: str) -> str:
    # PROMPT EFFECT: tells the model how vertical/square/landscape framing
    # should change *composition* of the image_prompt it writes (not just
    # the raw aspect ratio number, which models often ignore on its own).
    return {
        "vertical": "Full-bleed vertical composition, key subject centered "
                    "in the safe zone (avoid top/bottom 15% for UI overlays).",
        "square": "Balanced centered composition, works when cropped to a circle "
                  "thumbnail too.",
        "landscape": "Wide establishing composition, subject can sit left/right "
                     "third with room for text on the opposite side.",
        "portrait": "Vertical-leaning composition, subject fills more of the "
                    "frame height than width.",
    }.get(orientation, "")


def build_text_prompt(campaign: CampaignInput, platform: Platform) -> tuple[str, str]:
    """
    Returns (system_prompt, user_prompt) for a single platform.
    We generate one platform at a time so copy is genuinely tailored,
    not one generic post relabeled four times.

    ---- PROMPT EFFECT MAP (per UI field) ----

    campaign_goal:
        - Looks up GOAL_STRATEGY[goal]["focus"] -> added as "Strategic focus:"
          line. This is the single biggest lever: it silently steers which
          marketing framework (AIDA, PAS, Scarcity, etc.) the system prompt
          tells the model to pick, via preferred_frameworks (not sent
          verbatim, used implicitly by us to describe the focus).

    content_tone:
        - Looks up TONE_NOTES[tone] -> added as "Tone guidance:" line.
          Changes vocabulary/sentence rhythm instructions only, does not
          affect structure or length.

    target_audience:
        - Inserted verbatim as "TARGET AUDIENCE:" line. Free text, so the
          model reads it directly -- no transformation. This is why vague
          audience text produces vague targeting; specific text (age,
          interests, pain points) produces specific hooks.

    target_platforms / format:
        - See _platform_block() above. Each platform gets its own full
          generation pass (this function is called once per platform).

    key_message:
        - Inserted verbatim as "KEY MESSAGE (what we're marketing):" block.
          This is the factual anchor -- the instruction explicitly tells
          the model to ground copy in this text and avoid generic filler.

    optional brand inputs (company/industry/location/gender/age/colors/
    image_style):
        - Each populated field becomes one line in "BRAND / OPTIONAL
          CONTEXT:". Empty fields are omitted entirely (not sent as
          empty strings) to avoid diluting the prompt.
    """
    strategy = GOAL_STRATEGY[campaign.campaign_goal]
    tone_note = TONE_NOTES.get(campaign.content_tone.value, "")

    brand_lines = []
    opt = campaign.optional
    if opt.company_name:
        brand_lines.append(f"Company name: {opt.company_name}")
    if opt.industry:
        brand_lines.append(f"Industry: {opt.industry}")
    if opt.location:
        brand_lines.append(f"Location: {opt.location}")
    if opt.target_gender:
        brand_lines.append(f"Target gender skew: {opt.target_gender}")
    if opt.age_range:
        brand_lines.append(f"Target age range: {opt.age_range}")
    if opt.brand_colors:
        brand_lines.append(f"Brand colors: {', '.join(opt.brand_colors)}")
    if opt.image_style:
        brand_lines.append(f"Preferred image style: {opt.image_style}")
    brand_block = "\n".join(brand_lines) if brand_lines else "None provided."

    format_id = campaign.platform_formats.get(platform)
    fmt = get_platform_format(platform, format_id)

    # PROMPT EFFECT — text_on_image toggle:
    # Tells the model whether to compose the image with real marketing
    # text baked in (headline + CTA rendered inside the image, like a
    # finished ad) or keep it clean/photo-only.
    if campaign.text_on_image:
        # NOTE: even with the TYPOGRAPHY SPEC below, image models still make
        # occasional spelling/kerning/alignment mistakes baking text into a
        # raster image. Fine for fast internal previews; for production
        # creative, generate a clean (text_on_image=False) image and overlay
        # real vector text in a design tool or templating layer instead.
        text_on_image_note = (
            "TEXT_ON_IMAGE: ON. image_prompt must describe the exact headline/CTA "
            "text rendered directly in the image, verbatim from the headline/cta this "
            "same JSON response contains -- do not paraphrase it and do not describe "
            "printing it onto an in-scene prop, box, or sign as a substitute for a real "
            "overlay. Plan the headline to be short (ideally under 4 words per line, max "
            "2 lines) so it can render at a size that fits comfortably within 80% of the "
            "canvas width, starting no higher than 12% from the top edge, fully inside "
            "the frame with clear margin on all sides -- never touching or exceeding any "
            "edge, never partially cut off. All overlay text must share one consistent "
            "size/weight/color treatment within its own hierarchy tier (headline tier vs "
            "supporting/CTA tier) -- do not make any single word or number inside the "
            "headline dramatically larger or a different color than the rest of the "
            "headline. Bold, legible, on-brand placement, like a finished "
            "production-ready ad, not just a photo."
        )
    else:
        text_on_image_note = (
            "TEXT_ON_IMAGE: OFF. image_prompt must produce a clean photo/graphic with "
            "NO text baked in -- reserve negative space for text to be added later."
        )

    system_prompt = (
        "You are an expert marketing copywriter and ad strategist working inside a SaaS "
        "marketing content generator. You silently choose the best internal marketing "
        "framework (AIDA, PAS, FAB, Before-After-Bridge, Storytelling, Emotional Marketing, "
        "Scarcity, Authority, Social Proof, Loss Aversion, Benefit-Driven Messaging) based on "
        "the campaign goal below. Never mention the framework name in the output -- just apply it.\n\n"
        "Always respond with STRICT JSON ONLY. No markdown, no code fences, no commentary "
        "before or after the JSON object.\n\n"
        f"JSON schema to fill in exactly:\n{json.dumps(OUTPUT_SCHEMA_DESCRIPTION, indent=2)}"
    )

    user_prompt = (
        f"CAMPAIGN GOAL: {campaign.campaign_goal.value}\n"
        f"Strategic focus: {strategy['focus']}\n\n"
        f"CONTENT TONE: {campaign.content_tone.value}\n"
        f"Tone guidance: {tone_note}\n\n"
        f"TARGET AUDIENCE: {campaign.target_audience}\n\n"
        f"{_platform_block(platform, format_id)}\n"
        f"{text_on_image_note}\n\n"
        f"KEY MESSAGE (core idea, not the full image prompt):\n{campaign.key_message}\n\n"
        f"BRAND / OPTIONAL CONTEXT:\n{brand_block}\n\n"
        f"IMAGE_PROMPT INPUT MAP (use these exact values when covering the 20 required "
        f"categories for image_prompt -- do not invent unrelated details when a real "
        f"value is given here):\n"
        f"- Subject/scene anchor: {campaign.key_message}\n"
        f"- Goal-driven mood/atmosphere: {strategy['focus']}\n"
        f"- Tone-driven lighting/style: {tone_note}\n"
        f"- Audience context: {campaign.target_audience}\n"
        f"- Industry/location: {opt.industry or 'infer from audience'} / "
        f"{opt.location or 'infer from audience'}\n"
        f"- Brand integration: {opt.company_name or 'no brand name to show'}\n"
        f"- Color palette: {', '.join(opt.brand_colors) if opt.brand_colors else 'choose to fit tone/industry'}\n"
        f"- Style direction: {opt.image_style or 'choose to fit tone/industry'}\n"
        f"- Composition/orientation: {fmt['orientation']} ({fmt['aspect_ratio']})\n\n"
        "Generate content that is unique, conversion-aware, and native to this platform's "
        "conventions. Do not reuse generic filler like 'in today's fast-paced world'. "
        "Ground the copy in the specific key message above."
    )

    return system_prompt, user_prompt


def build_image_generation_prompt(image_prompt_text: str, aspect_ratio: str) -> str:
    """
    Final prompt actually sent to the image model. Wraps the LLM-authored
    image_prompt with hard technical/quality constraints, written as a
    strict spec (explicit safe-zone geometry, not vague "add padding"
    language) since diffusion image models follow concrete numeric/structural
    rules far more reliably than soft adjectives.

    Also embeds production-photography craft rules (lighting, optics,
    materials, typography) since describing the SCENE alone isn't enough --
    the model needs to be told how a real ad photo is actually produced,
    or it defaults to generic/CGI-ish output.
    """
    return (
        f"{image_prompt_text}\n\n"
        f"--- TECHNICAL SPEC (mandatory) ---\n"
        f"Aspect ratio: {aspect_ratio}. Professional advertising photography quality, "
        f"high resolution, sharp focus, no watermarks, no distorted logos, brand-safe.\n\n"
        f"--- PHOTOREALISM SPEC (mandatory) ---\n"
        f"Ultra photorealistic commercial advertising photography. Indistinguishable from "
        f"a professional DSLR or medium format camera capture.\n"
        f"Natural human anatomy with anatomically correct hands, fingers, faces, eyes, "
        f"ears, teeth, and body proportions.\n"
        f"Physically accurate lighting with global illumination, soft natural shadows, "
        f"realistic ambient occlusion, bounce lighting, and true color reflections.\n"
        f"Photorealistic skin textures with visible pores, subtle imperfections, realistic "
        f"hair strands, fabric weave, stitching, wrinkles, realistic wood grain, brick "
        f"texture, metal reflections, glass reflections, and natural weathering.\n"
        f"Accurate material rendering using physically based rendering (PBR) principles. "
        f"No plastic appearance, CGI look, waxy skin, oversaturated colors, or artificial "
        f"textures.\n"
        f"Professional commercial composition following the rule of thirds, balanced "
        f"visual hierarchy, realistic perspective, and natural focal length between 35mm "
        f"and 50mm.\n"
        f"High dynamic range with realistic highlight rolloff, detailed shadows, excellent "
        f"contrast, natural color grading, and premium commercial retouching.\n"
        f"Crisp edge definition with realistic depth of field, optical lens characteristics, "
        f"subtle background separation, and no excessive blur.\n"
        f"Marketing agency quality suitable for Fortune 500 advertising campaigns.\n\n"
        f"--- IMAGE QUALITY SPEC ---\n"
        f"8K resolution. Ultra sharp. Pixel perfect. Tack sharp focus. Noise free. "
        f"Artifact free. No AI generated appearance. No painterly effect. No illustration "
        f"style. No cartoon appearance. No CGI. No 3D render appearance. No blurry "
        f"textures. No duplicated objects. No warped geometry. No deformed hands. No "
        f"malformed faces. No floating objects. No extra limbs. No cropped people. No "
        f"compression artifacts. Professional magazine quality.\n\n"
        f"--- OVERLAY TEXT CONTRACT (mandatory, non-negotiable) ---\n"
        f"If overlay text was specified for this image, every one of those text strings "
        f"MUST appear verbatim, rendered as a genuine overlay layer on top of the photo "
        f"(like real ad typography), NOT reworded, NOT abbreviated, and NOT substituted "
        f"by printing similar wording onto an in-scene prop, package, or sign instead. "
        f"Printing the message on a box/label/screen in the scene does not satisfy the "
        f"overlay requirement -- the overlay text is a separate typographic layer above "
        f"the photograph. If multiple overlay lines were specified (e.g. headline + "
        f"supporting line + CTA), include ALL of them unless the safe-zone rules below "
        f"force you to drop the lowest-priority one -- omission is only allowed as that "
        f"explicit last resort, never as a silent substitution.\n\n"
        f"--- TEXT SAFE-ZONE SPEC (mandatory, treat as hard canvas rules) ---\n"
        f"Define the canvas edges at 0% (top/left) to 100% (bottom/right). ALL rendered "
        f"text -- every character, including ascenders/descenders and letter tops -- "
        f"must sit entirely within the inner safe zone: 10% to 90% horizontally, "
        f"12% to 88% vertically. Nothing may render in the outer 10-12% margin band. "
        f"The topmost pixel of the tallest character in the topmost line of text must "
        f"be no higher than 12% down from the top edge -- text starting at or near 0-5% "
        f"from the top is a hard violation, not a minor issue.\n\n"
        f"Text sizing: choose font size so the longest headline line, at full width, "
        f"fits within 80% of canvas width with room to spare -- never assume the canvas "
        f"is wider than it is. If a headline would need to run edge-to-edge or larger to "
        f"stay legible, shorten the wording or reduce font size instead of letting it "
        f"touch or exceed the safe zone.\n\n"
        f"Verify before finalizing: every letter of the first word and every letter of "
        f"the last word of each text line is fully rendered and fully inside the safe "
        f"zone -- no partial, sliced, or truncated characters at any edge.\n\n"
        f"Text hierarchy: max 2 distinct text sizes total across the whole image "
        f"(headline, one supporting line/CTA). A third, larger, differently-colored "
        f"numeral or word treated as its own hero element is a hierarchy violation even "
        f"if it's part of the headline's own wording -- keep numerals in the headline at "
        f"the same size/weight/color as the rest of the headline unless explicitly told "
        f"to emphasize them. No text element may overlap another text element, a face, "
        f"or hands.\n\n"
        f"If any of the above cannot be satisfied simultaneously, drop the lowest-priority "
        f"text element (supporting line first, then CTA) rather than violate the safe zone "
        f"-- but this is a last resort per the OVERLAY TEXT CONTRACT above, not a default.\n\n"
        f"--- FINAL SELF-AUDIT (perform mentally before output) ---\n"
        f"1. Does every specified overlay text string appear verbatim, as a true overlay, "
        f"not substituted onto a prop?\n"
        f"2. Is the topmost text character at or below 12% from the top edge?\n"
        f"3. Is all text within the 10-90% horizontal / 12-88% vertical safe zone with no "
        f"clipped characters at any edge?\n"
        f"4. Is there truly only 2 text sizes present, with no rogue oversized element?\n"
        f"5. Does the image read as an authentic photograph, not CGI/render/illustration?\n"
        f"If any answer is no, revise the composition before finalizing rather than "
        f"outputting a result that fails it.\n\n"
        f"--- TYPOGRAPHY SPEC ---\n"
        f"Typography must appear professionally designed by a senior graphic designer. "
        f"Perfect kerning. Perfect tracking. Perfect baseline alignment. Consistent line "
        f"spacing. Clean font rendering. No distorted letters. No misspelled words. No "
        f"merged characters. No broken glyphs. Text rendered with vector quality. Text "
        f"should integrate naturally into the scene without appearing pasted.\n\n"
        f"--- NEGATIVE PROMPT ---\n"
        f"Avoid CGI, 3D render, illustration, cartoon, painting, blurry details, low "
        f"resolution, over sharpening, noisy textures, distorted perspective, unrealistic "
        f"lighting, duplicate people, extra fingers, malformed hands, asymmetrical faces, "
        f"warped objects, floating objects, bad typography, cropped text, stretched "
        f"proportions, incorrect reflections, fake shadows, oversaturated colors, plastic "
        f"skin, wax textures, watermark, logo artifacts, random text, JPEG artifacts."
    )


def build_caption_regen_prompt(campaign: CampaignInput, platform: Platform, previous_caption: str) -> tuple[str, str]:
    """
    Regenerate button for the social post caption. Same context as the
    main prompt, told explicitly not to repeat the previous caption.
    """
    strategy = GOAL_STRATEGY[campaign.campaign_goal]
    tone_note = TONE_NOTES.get(campaign.content_tone.value, "")
    format_id = campaign.platform_formats.get(platform)

    system_prompt = (
        'You are an expert marketing copywriter. Respond with STRICT JSON ONLY: '
        '{"social_post": "string"}. No markdown, no commentary.'
    )
    user_prompt = (
        f"CAMPAIGN GOAL: {campaign.campaign_goal.value} ({strategy['focus']})\n"
        f"TONE: {campaign.content_tone.value} -- {tone_note}\n"
        f"TARGET AUDIENCE: {campaign.target_audience}\n"
        f"{_platform_block(platform, format_id)}\n"
        f"KEY MESSAGE: {campaign.key_message}\n\n"
        f"Previous caption (DO NOT repeat or closely paraphrase this):\n{previous_caption}\n\n"
        "Write one new social_post, same platform conventions, different angle/hook."
    )
    return system_prompt, user_prompt


def build_image_revision_prompt(
    campaign: CampaignInput, platform: Platform, previous_image_prompt: str, user_feedback: str
) -> tuple[str, str]:
    """
    "I don't like the image" flow: takes the previous AI-authored image_prompt
    plus the user's plain-English change request, and produces a revised
    image_prompt that keeps everything that wasn't complained about and
    changes only what was asked.
    """
    system_prompt = (
        'You are an expert AI image-prompt engineer. Respond with STRICT JSON ONLY: '
        '{"image_prompt": "string"}. No markdown, no commentary.'
    )
    user_prompt = (
        f"PREVIOUS IMAGE PROMPT:\n{previous_image_prompt}\n\n"
        f"USER'S REQUESTED CHANGES:\n{user_feedback}\n\n"
        "Rewrite the image prompt to incorporate the requested changes precisely. "
        "Keep every other detail (subject, setting, style, mood, composition) from "
        "the previous prompt intact unless the change request implies otherwise. "
        "If the previous image prompt above contains any technical/spec sections "
        "(headed with '---', e.g. TECHNICAL SPEC, PHOTOREALISM SPEC, SAFE-ZONE, "
        "TYPOGRAPHY, NEGATIVE PROMPT), ignore and discard those sections entirely -- "
        "they get re-added automatically. Output only the descriptive scene prompt "
        "itself, not any spec wrapper text."
    )
    return system_prompt, user_prompt


def build_headline_regen_prompt(
    campaign: CampaignInput, platform: Platform, previous_headlines: List[str]
) -> tuple[str, str]:
    """
    PROMPT EFFECT — regenerate button:
    Small, focused prompt (headlines only, not full post) that explicitly
    lists previously-seen headlines and instructs the model to avoid
    repeating them. Reuses the same goal/tone/audience/platform context
    so regenerated headlines stay on-strategy, not random.
    """
    strategy = GOAL_STRATEGY[campaign.campaign_goal]
    tone_note = TONE_NOTES.get(campaign.content_tone.value, "")
    format_id = campaign.platform_formats.get(platform)
    fmt = get_platform_format(platform, format_id)

    system_prompt = (
        "You are an expert marketing copywriter. Respond with STRICT JSON ONLY: "
        '{"primary": "string", "alternatives": ["string", "string"]}. '
        "No markdown, no commentary."
    )
    user_prompt = (
        f"CAMPAIGN GOAL: {campaign.campaign_goal.value} ({strategy['focus']})\n"
        f"TONE: {campaign.content_tone.value} -- {tone_note}\n"
        f"TARGET AUDIENCE: {campaign.target_audience}\n"
        f"PLATFORM: {platform.value}, format: {fmt['label']}\n"
        f"KEY MESSAGE: {campaign.key_message}\n\n"
        f"Previously generated headlines (DO NOT repeat these or close variants):\n"
        + "\n".join(f"- {h}" for h in previous_headlines)
        + "\n\nGenerate one new primary headline and 2 new alternatives."
    )
    return system_prompt, user_prompt