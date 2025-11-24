"""Common Pydantic models shared across DSV systems."""

from pydantic import BaseModel, Field


class Student(BaseModel):
    """Student model."""

    username: str
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    student_id: str | None = None
    program: str | None = None

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
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    title: str | None = None
    department: str | None = None
    room: str | None = None
    phone: str | None = None

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
    credits: float | None = None
    level: str | None = None
    period: str | None = None
    teachers: list[Teacher] = Field(default_factory=list)

    model_config = {"frozen": True}
