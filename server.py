"""
Internal test API. Run with:

    uvicorn server:app --reload --port 8000

Wraps MarketingContentGenerator so the plain-HTML frontend (static/index.html)
can call it over HTTP. Not hardened for production — internal use only,
per the note that this whole frontend gets swapped out later.
"""

from typing import Dict, List, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from models import CampaignGoal, ContentTone, Platform, ContentType, CampaignInput, OptionalBrandInputs
from generator import MarketingContentGenerator
from config import PLATFORM_FORMATS

app = FastAPI(title="Marketing Content Generator (internal)")

# Wide-open CORS since this only ever runs on localhost for internal testing.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve generated images so <img src="/generated_images/xyz.png"> works in the browser.
app.mount("/generated_images", StaticFiles(directory="generated_images", check_dir=False), name="images")
app.mount("/static", StaticFiles(directory="static", html=True), name="static")

_generator: Optional[MarketingContentGenerator] = None


def get_generator() -> MarketingContentGenerator:
    global _generator
    if _generator is None:
        _generator = MarketingContentGenerator()
    return _generator


# ---- request/response schemas ---------------------------------------------

class OptionalBrandInputsIn(BaseModel):
    company_name: Optional[str] = None
    brand_colors: Optional[List[str]] = None
    website_url: Optional[str] = None
    industry: Optional[str] = None
    location: Optional[str] = None
    target_gender: Optional[str] = None
    age_range: Optional[str] = None
    image_style: Optional[str] = None


class GenerateRequest(BaseModel):
    campaign_goal: str
    content_tone: str
    target_audience: str
    target_platforms: List[str]
    key_message: str
    content_types: List[str]
    platform_formats: Dict[str, str] = {}  # {"Instagram": "story", ...}
    text_on_image: bool = False
    optional: OptionalBrandInputsIn = OptionalBrandInputsIn()


class RegenerateHeadlineRequest(BaseModel):
    campaign_goal: str
    content_tone: str
    target_audience: str
    key_message: str
    platform: str
    platform_formats: Dict[str, str] = {}
    previous_headlines: List[str]


class RegenerateCaptionRequest(BaseModel):
    campaign_goal: str
    content_tone: str
    target_audience: str
    key_message: str
    platform: str
    platform_formats: Dict[str, str] = {}
    previous_caption: str


class RegenerateImageRequest(BaseModel):
    campaign_goal: str
    content_tone: str
    target_audience: str
    key_message: str
    platform: str
    platform_formats: Dict[str, str] = {}
    text_on_image: bool = False
    previous_image_prompt: str
    user_feedback: str


# ---- helpers ----------------------------------------------------------

def _build_campaign(req: GenerateRequest) -> CampaignInput:
    try:
        return CampaignInput(
            campaign_goal=CampaignGoal(req.campaign_goal),
            content_tone=ContentTone(req.content_tone),
            target_audience=req.target_audience,
            target_platforms=[Platform(p) for p in req.target_platforms],
            key_message=req.key_message,
            optional=OptionalBrandInputs(**req.optional.dict()),
            platform_formats={Platform(p): fmt for p, fmt in req.platform_formats.items()},
            text_on_image=req.text_on_image,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---- routes -------------------------------------------------------------

@app.get("/options")
def get_options():
    """Everything the frontend needs to build Step 1 dropdowns/toggles."""
    return {
        "campaign_goals": [g.value for g in CampaignGoal],
        "content_tones": [t.value for t in ContentTone],
        "platforms": [p.value for p in Platform],
        "content_types": [ct.value for ct in ContentType],
        "platform_formats": {
            platform.value: [
                {"id": f["id"], "label": f["label"], "aspect_ratio": f["aspect_ratio"], "orientation": f["orientation"]}
                for f in formats
            ]
            for platform, formats in PLATFORM_FORMATS.items()
        },
    }


@app.post("/generate")
def generate(req: GenerateRequest):
    campaign = _build_campaign(req)
    try:
        content_types = [ContentType(ct) for ct in req.content_types]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        results = get_generator().generate(campaign, content_types)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"results": results}


@app.post("/regenerate-headline")
def regenerate_headline(req: RegenerateHeadlineRequest):
    try:
        campaign = CampaignInput(
            campaign_goal=CampaignGoal(req.campaign_goal),
            content_tone=ContentTone(req.content_tone),
            target_audience=req.target_audience,
            target_platforms=[Platform(req.platform)],
            key_message=req.key_message,
            platform_formats={Platform(p): fmt for p, fmt in req.platform_formats.items()},
        )
        platform = Platform(req.platform)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        headlines = get_generator().regenerate_headlines(campaign, platform, req.previous_headlines)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"headlines": headlines}


@app.post("/regenerate-caption")
def regenerate_caption(req: RegenerateCaptionRequest):
    try:
        campaign = CampaignInput(
            campaign_goal=CampaignGoal(req.campaign_goal),
            content_tone=ContentTone(req.content_tone),
            target_audience=req.target_audience,
            target_platforms=[Platform(req.platform)],
            key_message=req.key_message,
            platform_formats={Platform(p): fmt for p, fmt in req.platform_formats.items()},
        )
        platform = Platform(req.platform)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        caption = get_generator().regenerate_caption(campaign, platform, req.previous_caption)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"social_post": caption}


@app.post("/regenerate-image")
def regenerate_image(req: RegenerateImageRequest):
    try:
        campaign = CampaignInput(
            campaign_goal=CampaignGoal(req.campaign_goal),
            content_tone=ContentTone(req.content_tone),
            target_audience=req.target_audience,
            target_platforms=[Platform(req.platform)],
            key_message=req.key_message,
            platform_formats={Platform(p): fmt for p, fmt in req.platform_formats.items()},
            text_on_image=req.text_on_image,
        )
        platform = Platform(req.platform)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        image_path, final_image_prompt, revised_prompt = get_generator().regenerate_image(
            campaign, platform, req.previous_image_prompt, req.user_feedback
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"image_path": image_path, "final_image_prompt": final_image_prompt, "raw_image_prompt": revised_prompt}