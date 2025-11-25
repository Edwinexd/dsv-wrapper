"""Pydantic models for Clickmap (DSV office/workspace placement map)."""

from pydantic import BaseModel, Field


class Placement(BaseModel):
    """Workspace placement on the DSV floor map.

    Represents a single workspace/desk position with associated person information.
    """

    id: str = Field(description="Unique identifier (UUID)")
    place_name: str = Field(description="Workspace/room identifier (e.g., '66109', '6:7')")
    person_name: str = Field(default="", description="Name of person at this workspace")
    person_role: str = Field(default="", description="Title/role of the person")
    latitude: float = Field(description="Y coordinate on the map")
    longitude: float = Field(description="X coordinate on the map")
    comment: str = Field(default="", description="Additional notes (admin only)")

    model_config = {"frozen": True}

    @property
    def is_occupied(self) -> bool:
        """Check if this workspace has a person assigned."""
        return bool(self.person_name)
