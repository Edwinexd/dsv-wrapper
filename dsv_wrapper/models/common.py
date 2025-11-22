"""Common Pydantic models shared across DSV systems."""

from typing import Optional

from pydantic import BaseModel, Field


class Student(BaseModel):
    """Student model."""

    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    student_id: Optional[str] = None
    program: Optional[str] = None

    model_config = {"frozen": True}

    @property
    def full_name(self) -> str:
        """Get full name."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username


class Teacher(BaseModel):
    """Teacher model."""

    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    title: Optional[str] = None
    department: Optional[str] = None
    room: Optional[str] = None
    phone: Optional[str] = None

    model_config = {"frozen": True}

    @property
    def full_name(self) -> str:
        """Get full name."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username


class Course(BaseModel):
    """Course model."""

    code: str
    name: str
    credits: Optional[float] = None
    level: Optional[str] = None
    period: Optional[str] = None
    teachers: list[Teacher] = Field(default_factory=list)

    model_config = {"frozen": True}
