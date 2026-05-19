"""Common Pydantic models shared across DSV systems."""

from pydantic import BaseModel, Field


class Student(BaseModel):
    """Student model.

    ``username`` is the SU/KTH login (e.g. ``ekke4862@SU.SE``). Search-result
    rows don't include it (only the profile page does), so it is optional —
    call :meth:`get_username` to resolve it on demand.
    """

    username: str | None = None
    person_id: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    student_id: str | None = None
    program: str | None = None
    profile_url: str | None = None
    address: str | None = None

    # Mutable so :meth:`get_username` can cache its result.
    model_config = {"frozen": False}

    @property
    def full_name(self) -> str:
        """Get full name."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username or ""

    def get_username(self, client: "DaisyClient") -> str:  # type: ignore[name-defined]  # noqa: F821
        """Return SU username, fetching the student profile if necessary.

        - If :attr:`username` is already set, returns it.
        - Otherwise needs :attr:`person_id`, fetches
          ``/anstalld/student/studentinfo.jspa?personID=N``, parses the
          ``Användarnamn`` field, caches it, and returns it.

        Raises:
            AmbiguousMatchError: If ``person_id`` is missing or the profile
                page does not surface a username (some external/exchange
                students have no SU login yet).
        """
        if self.username:
            return self.username
        from ..exceptions import AmbiguousMatchError

        if not self.person_id:
            raise AmbiguousMatchError(
                f"Cannot resolve username for {self.full_name!r}: no personID"
            )
        full = client.get_student_details(self.person_id)
        if not full.username:
            raise AmbiguousMatchError(f"Student profile {self.person_id} has no SU username")
        object.__setattr__(self, "username", full.username)
        # Opportunistically backfill anything else still empty.
        for field in ("email", "phone", "first_name", "last_name", "address", "profile_url"):
            if getattr(self, field) is None and getattr(full, field) is not None:
                object.__setattr__(self, field, getattr(full, field))
        return full.username

    async def aget_username(
        self,
        client: "AsyncDaisyClient",  # type: ignore[name-defined]  # noqa: F821
    ) -> str:
        """Async sibling of :meth:`get_username`."""
        if self.username:
            return self.username
        from ..exceptions import AmbiguousMatchError

        if not self.person_id:
            raise AmbiguousMatchError(
                f"Cannot resolve username for {self.full_name!r}: no personID"
            )
        full = await client.get_student_details(self.person_id)
        if not full.username:
            raise AmbiguousMatchError(f"Student profile {self.person_id} has no SU username")
        object.__setattr__(self, "username", full.username)
        for field in ("email", "phone", "first_name", "last_name", "address", "profile_url"):
            if getattr(self, field) is None and getattr(full, field) is not None:
                object.__setattr__(self, field, getattr(full, field))
        return full.username


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
