"""Pydantic models for Daisy system."""

import re
from collections.abc import Callable
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


class RoomTime(int, Enum):
    """Time slots for room bookings (24-hour format)."""

    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    ELEVEN = 11
    TWELVE = 12
    THIRTEEN = 13
    FOURTEEN = 14
    FIFTEEN = 15
    SIXTEEN = 16
    SEVENTEEN = 17
    EIGHTEEN = 18
    NINETEEN = 19
    TWENTY = 20
    TWENTY_ONE = 21
    TWENTY_TWO = 22
    TWENTY_THREE = 23

    def to_string(self) -> str:
        """Convert to HH:00 format."""
        if self.value < 10:
            return f"0{self.value}:00"
        return f"{self.value}:00"

    def __lt__(self, other):
        return self.value < other.value

    def __le__(self, other):
        return self.value <= other.value

    def __eq__(self, other):
        return self.value == other.value

    def __ne__(self, other):
        return self.value != other.value

    def __gt__(self, other):
        return self.value > other.value

    def __ge__(self, other):
        return self.value >= other.value


class RoomCategory(int, Enum):
    """Room categories in Daisy with their numeric IDs."""

    VISITORS_MEETING_ROOMS = 81
    COMPUTER_LABS = 66
    DISTANCE_AND_RECORDING_STUDIOS = 95
    BOOKABLE_GROUP_ROOMS = 68
    NON_BOOKABLE_GROUP_ROOMS = 77
    MEDIA_PRODUCTION = 76
    PROJECT_MEETING_ROOMS = 82
    STAFF_MEETING_ROOMS = 71
    SEMINAR_ROOMS = 67
    STUDENT_LAB = 65
    TEACHING_ROOMS = 64

    def to_string(self) -> str:
        """Convert to string for API calls."""
        return str(self.value)


class Room(int, Enum):
    """Rooms in Daisy with their numeric IDs."""

    # Bookable group rooms
    G10_1 = 633
    G10_2 = 634
    G10_3 = 635
    G10_4 = 636
    G10_5 = 637
    G10_6 = 638
    G10_7 = 639
    G5_1 = 815
    G5_10 = 804
    G5_11 = 805
    G5_12 = 795
    G5_13 = 814
    G5_15 = 812
    G5_16 = 811
    G5_17 = 810
    G5_2 = 796
    G5_3 = 797
    G5_4 = 798
    G5_5 = 799
    G5_6 = 800
    G5_7 = 801
    G5_8 = 802
    G5_9 = 803
    # Visitors meeting rooms
    F1 = 840
    F2 = 839
    F3 = 838
    # Computer labs
    D1 = 625
    D2 = 626
    D3 = 627
    D4 = 628
    # Distance and recording studios
    IDEAL_STUDIO = 790
    SMALL_STUDIO = 1275
    # Unbookable group rooms
    G10_8 = 640
    G5_14 = 813
    G5_18 = 809
    G5_19 = 808
    G5_20 = 807
    G5_21 = 806
    # Media production
    P1 = 652
    P2 = 653
    P3 = 654
    STUDENTLABB_MEDIA = 651
    STUDIO = 655
    # Project meeting rooms
    PROJECT_ZONE_2 = 1257
    PROJECT_ZONE_5 = 1258
    # Meeting rooms
    M10 = 817
    M20 = 820
    M6_1 = 823
    M6_2 = 822
    M6_3 = 821
    M6_4 = 824
    M6_5 = 825
    M6_6 = 819
    M8 = 818
    # Seminar rooms
    S1 = 629
    S2 = 630
    S3 = 631
    # Student lab
    STUDENTLABB_ID_RIGHT = 648
    STUDENTLABB_ID_LEFT = 1378
    STUDENTLABB_ID_FIX = 1382
    STUDENTLABB_GAME = 1394
    STUDENTLABB_GAME_2022 = 649
    STUDENTLABB_GAME_EXTRA_2022 = 869
    STUDENTLABB_SECURITY = 650
    # Teaching rooms
    AUDITORIUM_NOD = 620
    DL_40 = 632
    L30 = 622
    L50 = 623
    L70 = 624
    SMALL_AUDITORIUM = 621

    @classmethod
    def from_name(cls, name: str):
        """Get room enum from room name string."""
        return {
            "G10:1": cls.G10_1,
            "G10:2": cls.G10_2,
            "G10:3": cls.G10_3,
            "G10:4": cls.G10_4,
            "G10:5": cls.G10_5,
            "G10:6": cls.G10_6,
            "G10:7": cls.G10_7,
            "G5:1": cls.G5_1,
            "G5:10": cls.G5_10,
            "G5:11": cls.G5_11,
            "G5:12": cls.G5_12,
            "G5:13": cls.G5_13,
            "G5:15": cls.G5_15,
            "G5:16": cls.G5_16,
            "G5:17": cls.G5_17,
            "G5:2": cls.G5_2,
            "G5:3": cls.G5_3,
            "G5:4": cls.G5_4,
            "G5:5": cls.G5_5,
            "G5:6": cls.G5_6,
            "G5:7": cls.G5_7,
            "G5:8": cls.G5_8,
            "G5:9": cls.G5_9,
            # Foaje
            "Foaje F1": cls.F1,
            "Foaje F2": cls.F2,
            "Foaje F3": cls.F3,
            # Datorsalar
            "D1": cls.D1,
            "D2": cls.D2,
            "D3": cls.D3,
            "D4": cls.D4,
            # Distans och inspelningsstudios
            "IDEAL-studion": cls.IDEAL_STUDIO,
            "Lilla studion": cls.SMALL_STUDIO,
            # Unbookable group rooms
            "G10:8": cls.G10_8,
            "G5:14": cls.G5_14,
            "G5:18": cls.G5_18,
            "G5:19": cls.G5_19,
            "G5:20": cls.G5_20,
            "G5:21": cls.G5_21,
            # Mediaproduktion
            "Produktion 1": cls.P1,
            "Produktion 2": cls.P2,
            "Produktion 3": cls.P3,
            "Studentlabb Media": cls.STUDENTLABB_MEDIA,
            "Studio": cls.STUDIO,
            # Projektmötesrum
            "Projektmöte Zon 2": cls.PROJECT_ZONE_2,
            "Projektmöte Zon 5": cls.PROJECT_ZONE_5,
            # Mötesrum
            "M10": cls.M10,
            "M20": cls.M20,
            "M6:1": cls.M6_1,
            "M6:2": cls.M6_2,
            "M6:3": cls.M6_3,
            "M6:4": cls.M6_4,
            "M6:5": cls.M6_5,
            "M6:6": cls.M6_6,
            "M8": cls.M8,
            # Seminarierum
            "S1": cls.S1,
            "S2": cls.S2,
            "S3": cls.S3,
            # Studentlabb
            "Studentlabb ID Höger": cls.STUDENTLABB_ID_RIGHT,
            "Studentlabb ID Vänster": cls.STUDENTLABB_ID_LEFT,
            "Studentlabb ID:fix": cls.STUDENTLABB_ID_FIX,
            "Studentlabb Spel": cls.STUDENTLABB_GAME,
            "Studentlabb Spel (-2022)": cls.STUDENTLABB_GAME_2022,
            "Studentlabb Spel extra (-2022)": cls.STUDENTLABB_GAME_EXTRA_2022,
            "Studentlabb Säkerhet": cls.STUDENTLABB_SECURITY,
            # Undervisningsrum
            "Aula NOD": cls.AUDITORIUM_NOD,
            "DL40": cls.DL_40,
            "L30": cls.L30,
            "L50": cls.L50,
            "L70": cls.L70,
            "Lilla Hörsalen": cls.SMALL_AUDITORIUM,
        }[name]


class RoomRestriction(int, Enum):
    """Room restrictions for filtering available rooms."""

    G10_ROOM = 0
    G5_ROOM = 1
    GREEN_AREA = 2
    RED_AREA = 3

    def to_string(self) -> str:
        """Convert to string."""
        return str(self.value)

    def to_filter(self) -> Callable[[Room], bool]:
        """Get filter function for this restriction."""
        if self == RoomRestriction.G10_ROOM:
            return lambda room: room in [
                Room.G10_1,
                Room.G10_2,
                Room.G10_3,
                Room.G10_4,
                Room.G10_5,
                Room.G10_6,
                Room.G10_7,
                Room.G10_8,
            ]
        if self == RoomRestriction.G5_ROOM:
            return lambda room: room in [
                Room.G5_1,
                Room.G5_10,
                Room.G5_11,
                Room.G5_12,
                Room.G5_13,
                Room.G5_15,
                Room.G5_16,
                Room.G5_17,
                Room.G5_2,
                Room.G5_3,
                Room.G5_4,
                Room.G5_5,
                Room.G5_6,
                Room.G5_7,
                Room.G5_8,
                Room.G5_9,
                Room.G5_14,
                Room.G5_19,
                Room.G5_20,
                Room.G5_21,
            ]
        if self == RoomRestriction.GREEN_AREA:
            return lambda room: room in [
                Room.G10_1,
                Room.G10_2,
                Room.G10_3,
                Room.G10_4,
                Room.G10_5,
                Room.G5_1,
                Room.G5_10,
                Room.G5_11,
                Room.G5_12,
                Room.G5_2,
                Room.G5_3,
                Room.G5_4,
                Room.G5_5,
                Room.G5_6,
                Room.G5_7,
                Room.G5_8,
                Room.G5_9,
            ]
        if self == RoomRestriction.RED_AREA:
            return lambda room: room in [
                Room.G10_6,
                Room.G10_7,
                Room.G5_13,
                Room.G5_15,
                Room.G5_16,
                Room.G5_17,
                Room.G10_8,
                Room.G5_14,
                Room.G5_18,
                Room.G5_19,
                Room.G5_20,
                Room.G5_21,
            ]

        raise KeyError(f"Unknown restriction {self}")


class BookingSlot(BaseModel):
    """Booking time slot for a specific room."""

    room: Room
    from_time: RoomTime
    to_time: RoomTime

    model_config = {"frozen": True}


class RoomActivity(BaseModel):
    """Activity scheduled in a room."""

    time_slot_start: RoomTime
    time_slot_end: RoomTime
    event: str

    model_config = {"frozen": True}


class BookableRoom(BaseModel):
    """Room with its booked time slots."""

    room: Room
    booked_slots: list[RoomActivity]

    model_config = {"frozen": True}


class Schedule(BaseModel):
    """Schedule for a room category on a specific date."""

    activities: dict[str, list[RoomActivity]]
    room_category_title: str
    room_category_id: int
    room_category: RoomCategory
    datetime: datetime

    model_config = {"frozen": True}


class Break(BaseModel):
    """Break period in a schedule."""

    start_time: RoomTime
    duration: int

    model_config = {"frozen": True}


class InstitutionID(str, Enum):
    """Institution IDs in Daisy.

    Note: Daisy is DSV-only. The institution_id parameter exists in forms
    but DSV is the only supported value.
    """

    DSV = "4"


class ActivityType(str, Enum):
    """Activity types in room schedules."""

    LECTURE = "Föreläsning"
    SEMINAR = "Seminarium"
    EXERCISE = "Övning"
    EXAMINATION = "Tentamen"
    PROJECT = "Projektarbete"
    OTHER = "Övrigt"


class TermSeason(str, Enum):
    """Daisy term seasons. VT = vårtermin (spring), HT = hösttermin (autumn)."""

    VT = "VT"
    HT = "HT"


class Semester(BaseModel):
    """A Daisy semester (e.g. VT2026, HT2025).

    Daisy encodes semesters as 5-digit IDs: ``YYYY`` followed by ``1`` (VT) or ``2`` (HT).
    VT2026 → ``20261``, HT2026 → ``20262``.
    """

    year: int
    season: TermSeason

    model_config = {"frozen": True}

    @property
    def termin_id(self) -> str:
        """Daisy termID (e.g. '20261' for VT2026)."""
        suffix = "1" if self.season is TermSeason.VT else "2"
        return f"{self.year}{suffix}"

    @property
    def label(self) -> str:
        """Human label like 'VT2026'."""
        return f"{self.season.value}{self.year}"

    def __str__(self) -> str:
        return self.label

    @classmethod
    def from_label(cls, label: str) -> "Semester":
        """Parse 'VT2026' / 'HT2025' (case-insensitive)."""
        label = label.strip().upper()
        if len(label) < 3 or label[:2] not in {"VT", "HT"}:
            raise ValueError(f"Invalid semester label: {label!r}")
        try:
            year = int(label[2:])
        except ValueError as e:
            raise ValueError(f"Invalid year in semester label: {label!r}") from e
        return cls(year=year, season=TermSeason(label[:2]))

    @classmethod
    def from_termin_id(cls, termin_id: str | int) -> "Semester":
        """Parse a Daisy termID like '20261' or 20261."""
        s = str(termin_id)
        if len(s) != 5 or s[-1] not in {"1", "2"}:
            raise ValueError(f"Invalid termin_id: {termin_id!r}")
        year = int(s[:4])
        season = TermSeason.VT if s[-1] == "1" else TermSeason.HT
        return cls(year=year, season=season)


class DaisyCourse(BaseModel):
    """A course offering ("moment"/"delkurs" instance) in Daisy.

    Represents a specific delivery of a course in a particular semester.
    Fields with ``None`` typically mean the data was not present on the page
    used to construct the model — call :meth:`DaisyClient.get_course` to
    fetch the full detail page.
    """

    momenttillf_id: str = Field(description="Daisy momenttillfID (e.g. '7620')")
    beteckning: str = Field(description="Course code/designation (e.g. 'PROG2')")
    name: str = Field(description="Course name in Swedish")
    ects: float | None = Field(default=None, description="Credits (högskolepoäng)")
    semester: Semester | None = None
    start_date: date | None = None
    end_date: date | None = None
    info_url: str | None = Field(default=None, description="Public momentinfo URL")
    schedule_url: str | None = Field(default=None, description="Schedule URL")
    participants_url: str | None = Field(default=None, description="Deltagarlista URL")
    syllabus_url: str | None = Field(
        default=None,
        description="External syllabus URL (utbildning.su.se planarkiv) — only from detail page",
    )
    unit: str | None = Field(default=None, description="Owning unit, e.g. 'ACT' — only from detail")

    model_config = {"frozen": True}


class CourseStaff(BaseModel):
    """A person involved in teaching/administering a course offering.

    Sourced from the public ``/servlet/momentinfo.Momentinfo`` page, which
    groups people under free-text role headings (e.g. *Kurs-/delkursansvarig*,
    *Examination*, *Handledare*, *Laborationsledare*, *Administration*).
    A single person can appear under multiple headings; we merge them into
    :attr:`roles` so each person shows up once with all their roles.

    Some participants (typically student-handledare) appear on the public page
    as plain text, without a profile link. For those we capture name + roles
    but :attr:`person_id` is ``None``. Call :meth:`get_person_id` to resolve
    them via Daisy's student search.

    Daisy links employed staff to ``/anstalld/anstalldinfo.jspa`` and student
    tutors to ``/anstalld/student/studentinfo.jspa`` (and some employed people
    keep a legacy student-URL link — e.g. former PhDs). The URL alone is not
    a reliable indicator of current employment, so we don't model it as a
    boolean; :meth:`get_details` returns either a :class:`Staff` or a
    :class:`StudentInfo` based on the URL flavour, and you can pattern-match
    on the result.
    """

    name: str = Field(description="Full display name as shown on the course page")
    first_name: str | None = Field(
        default=None, description="First-name component, parsed from 'name'"
    )
    last_name: str | None = Field(
        default=None, description="Last-name component, parsed from 'name'"
    )
    person_id: str | None = Field(
        default=None,
        description=(
            "Daisy personID. ``None`` for participants listed as plain text "
            "without a profile link — call :meth:`get_person_id` to resolve."
        ),
    )
    profile_url: str | None = None
    roles: list[str] = Field(
        default_factory=list,
        description=(
            "Role headings this person appears under on the course page. "
            "Free-text Swedish strings — common ones: 'Kurs-/delkursansvarig', "
            "'Examination', 'Handledare', 'Laborationsledare', 'Administration'."
        ),
    )

    # Mutable so :meth:`get_person_id` can cache its result.
    model_config = {"frozen": False}

    def _name_split_attempts(self) -> list[tuple[str, str]]:
        """Yield (first_name, last_name) candidate splits to try in order.

        Daisy stores the boundary inconsistently for multi-word names. The
        default split (everything-but-last vs last token) handles hyphenated
        first names like ``Andrés-Emilio Miranda``. The fallback (first token
        vs the rest) catches multi-word surnames like ``Fathi Tachinabadi``.
        """
        if not self.first_name or not self.last_name:
            return []
        attempts: list[tuple[str, str]] = [(self.first_name, self.last_name)]
        # Build the alt split from the original full name, not from the
        # already-split fields — handles cases like "Mats Karlsson Landré".
        tokens = [t for t in re.split(r"\s+", self.name.strip()) if t]
        if len(tokens) >= 3:
            alt = (tokens[0], " ".join(tokens[1:]))
            if alt != attempts[0]:
                attempts.append(alt)
        return attempts

    def get_person_id(self, client: "DaisyClient") -> str:  # type: ignore[name-defined]  # noqa: F821
        """Return Daisy ``personID``, resolving via student search if needed.

        - If :attr:`person_id` is already set (from the page link), returns it.
        - Otherwise POSTs ``firstname`` + ``lastname`` to the student search;
          if that returns 0 hits and the name has ≥3 tokens, retries once
          with the alternate split (first token / remainder).
        - Requires exactly one hit, caches the resolved id on this instance.

        Raises:
            AmbiguousMatchError: If both attempts return 0 or >1 hits, or if
                this instance has no parsed first/last name.
        """
        if self.person_id is not None:
            return self.person_id
        from ..exceptions import AmbiguousMatchError

        attempts = self._name_split_attempts()
        if not attempts:
            raise AmbiguousMatchError(
                f"Cannot resolve {self.name!r}: missing first/last name split"
            )
        last_count = None
        for first, last in attempts:
            hits = client.search_students(first_name=first, last_name=last)
            if len(hits) == 1 and hits[0].person_id:
                object.__setattr__(self, "person_id", hits[0].person_id)
                if hits[0].profile_url and self.profile_url is None:
                    object.__setattr__(self, "profile_url", hits[0].profile_url)
                return hits[0].person_id
            last_count = len(hits)
        raise AmbiguousMatchError(
            f"Student search for {self.name!r} returned {last_count} matches "
            f"(expected exactly 1) after trying {len(attempts)} name splits"
        )

    async def aget_person_id(
        self,
        client: "AsyncDaisyClient",  # type: ignore[name-defined]  # noqa: F821
    ) -> str:
        """Async sibling of :meth:`get_person_id`."""
        if self.person_id is not None:
            return self.person_id
        from ..exceptions import AmbiguousMatchError

        attempts = self._name_split_attempts()
        if not attempts:
            raise AmbiguousMatchError(
                f"Cannot resolve {self.name!r}: missing first/last name split"
            )
        last_count = None
        for first, last in attempts:
            hits = await client.search_students(first_name=first, last_name=last)
            if len(hits) == 1 and hits[0].person_id:
                object.__setattr__(self, "person_id", hits[0].person_id)
                if hits[0].profile_url and self.profile_url is None:
                    object.__setattr__(self, "profile_url", hits[0].profile_url)
                return hits[0].person_id
            last_count = len(hits)
        raise AmbiguousMatchError(
            f"Student search for {self.name!r} returned {last_count} matches "
            f"(expected exactly 1) after trying {len(attempts)} name splits"
        )


class CourseResponsibility(BaseModel):
    """A staff member's course-responsibility entry as listed on their profile."""

    semester: Semester
    beteckningar: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}


class Staff(BaseModel):
    """Staff/employee model for Daisy.

    The basic identification fields come from search results; the richer
    fields (address, usernames, office_hours, …) come from the individual
    profile page returned by :meth:`DaisyClient.get_staff_details`. Call
    :meth:`get_usernames` to fetch them lazily when starting from a search
    result.
    """

    person_id: str
    name: str
    email: str | None = None
    room: str | None = None
    location: str | None = None
    profile_url: str | None = None
    profile_pic_url: str | None = None
    units: list[str] = Field(default_factory=list)
    swedish_title: str | None = None
    english_title: str | None = None
    phone: str | None = None
    usernames: list[str] = Field(
        default_factory=list, description="One or more login names (KTH/SU/DSV realm-prefixed)"
    )
    address: str | None = None
    home_phone: str | None = None
    alt_phone: str | None = None
    office_hours: str | None = Field(default=None, description="Mottagningstid free-text")
    exam_systems: list[str] = Field(
        default_factory=list,
        description="Examination systems the staff member is trained for (e.g. 'iExam')",
    )
    research_areas: list[str] = Field(default_factory=list)
    website: str | None = None
    course_responsibilities: list[CourseResponsibility] = Field(default_factory=list)

    # Mutable so :meth:`get_usernames` can cache its result.
    model_config = {"frozen": False}

    def get_usernames(self, client: "DaisyClient") -> list[str]:  # type: ignore[name-defined]  # noqa: F821
        """Return staff logins, fetching the profile page if needed.

        - If :attr:`usernames` already has entries, returns them.
        - Otherwise fetches ``/anstalld/anstalldinfo.jspa?personID=N``,
          replaces this instance's fields with the full profile, and
          returns the resolved usernames.

        Raises:
            AmbiguousMatchError: If the profile page surfaces no usernames
                (occasionally true for accounts pending provisioning).
        """
        if self.usernames:
            return self.usernames
        from ..exceptions import AmbiguousMatchError

        full = client.get_staff_details(self.person_id)
        if not full.usernames:
            raise AmbiguousMatchError(f"Staff profile {self.person_id} has no usernames")
        # Backfill every field this instance has left blank.
        for field in full.model_fields:
            current = getattr(self, field)
            new = getattr(full, field)
            if current in (None, "", [], ()):
                object.__setattr__(self, field, new)
        return full.usernames

    async def aget_usernames(
        self,
        client: "AsyncDaisyClient",  # type: ignore[name-defined]  # noqa: F821
    ) -> list[str]:
        """Async sibling of :meth:`get_usernames`."""
        if self.usernames:
            return self.usernames
        from ..exceptions import AmbiguousMatchError

        full = await client.get_staff_details(self.person_id)
        if not full.usernames:
            raise AmbiguousMatchError(f"Staff profile {self.person_id} has no usernames")
        for field in full.model_fields:
            current = getattr(self, field)
            new = getattr(full, field)
            if current in (None, "", [], ()):
                object.__setattr__(self, field, new)
        return full.usernames
