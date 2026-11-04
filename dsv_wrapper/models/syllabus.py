"""Models for the public SU course syllabus archive (planarkiv)."""

from typing import Literal

from pydantic import BaseModel, Field

from .daisy import Semester


class SyllabusLink(BaseModel):
    """A titled link from the syllabus archive."""

    text: str
    url: str

    model_config = {"frozen": True}


class SyllabusVersion(BaseModel):
    """One published version of a course syllabus (kursplan).

    Each version is a PDF valid from ``semester`` onwards, until a newer
    version replaces it. Versions are immutable as far as the archive is
    concerned; a revision is published as a new version.
    """

    semester: Semester = Field(description="Semester the version is valid from")
    language: Literal["sv", "en"] = Field(description="Language of the PDF")
    pdf_url: str = Field(description="albatross.it.su.se PDF URL")
    title: str = Field(description="Link text, e.g. 'Utbildningsplan Hösttermin 2020'")

    model_config = {"frozen": True}


class LiteratureList(BaseModel):
    """Literature lists published for one semester."""

    semester: str = Field(description="Semester label as shown by the archive")
    links: list[SyllabusLink] = Field(default_factory=list)

    model_config = {"frozen": True}


class SyllabusArchiveEntry(BaseModel):
    """A course (or programme) in the syllabus archive with all its versions."""

    code: str = Field(description="Ladok course code, e.g. 'IB440C'")
    name: str = Field(description="Course name in the requested language")
    education_type: str = Field(description="E.g. 'course' or 'programme'")
    ects: float | None = Field(default=None, description="Credits (högskolepoäng)")
    description: str | None = Field(
        default=None, description="Kind, level, subject and department as one line"
    )
    is_discontinued: bool = False
    department: SyllabusLink | None = None
    versions: list[SyllabusVersion] = Field(
        default_factory=list, description="Newest first, as listed by the archive"
    )
    literature_lists: list[LiteratureList] = Field(default_factory=list)

    model_config = {"frozen": True}

    @property
    def latest(self) -> SyllabusVersion | None:
        """The version with the most recent start semester."""
        if not self.versions:
            return None
        return max(self.versions, key=lambda v: v.semester.termin_id)
