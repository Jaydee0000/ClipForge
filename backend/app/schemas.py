from pydantic import BaseModel, Field


class ClipRequest(BaseModel):
    video_id: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    title: str = "Untitled clip"


class AnalyzeRequest(BaseModel):
    video_id: str
    instructions: str = Field(min_length=3)


class SuggestedClip(BaseModel):
    start: float
    end: float
    title: str
    reason: str
    clip_url: str | None = None
