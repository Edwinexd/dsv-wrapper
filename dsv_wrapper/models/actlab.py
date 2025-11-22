"""Pydantic models for ACT Lab system."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Slide(BaseModel):
    """Digital signage slide model."""

    id: str
    name: str
    filename: Optional[str] = None
    show_id: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    auto_delete: bool = False
    upload_time: Optional[datetime] = None

    model_config = {"frozen": True}


class Show(BaseModel):
    """Digital signage show model."""

    id: str
    name: str
    slides: list[Slide] = Field(default_factory=list)
    description: Optional[str] = None

    model_config = {"frozen": True}

    @property
    def slide_count(self) -> int:
        """Get number of slides in show."""
        return len(self.slides)


class SlideUploadResult(BaseModel):
    """Result of a slide upload operation."""

    success: bool
    slide_id: Optional[str] = None
    message: Optional[str] = None

    model_config = {"frozen": True}
