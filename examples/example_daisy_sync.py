"""Example: Using Daisy client synchronously."""

from datetime import date

from dsv_wrapper import AmbiguousMatchError, DaisyClient, RoomCategory, Semester

# Initialize the Daisy client
USERNAME = "your_username"
PASSWORD = "your_password"

with DaisyClient(username=USERNAME, password=PASSWORD, service="daisy_staff") as daisy:
    print("=== Daisy Client Example ===\n")

    # Get room schedule for today
    print("1. Getting room schedule for bookable group rooms...")
    schedule = daisy.get_schedule(RoomCategory.BOOKABLE_GROUP_ROOMS, date.today())
    print(f"Schedule: {schedule.room_category_title}")
    print(f"Date: {schedule.datetime.date()}")
    print(f"Rooms: {len(schedule.activities)}")

    # Display activities
    print("\nRoom activities:")
    for room_name, activities in list(schedule.activities.items())[:3]:  # Show first 3 rooms
        print(f"\n  {room_name}")
        if activities:
            for activity in activities[:5]:  # Show first 5 activities
                start = activity.time_slot_start.to_string()
                end = activity.time_slot_end.to_string()
                print(f"    {start} - {end}: {activity.event}")
        else:
            print("    No activities")

    # Search students by full first+last name
    print("\n2. Searching for a student...")
    students = daisy.search_students(first_name="Edwin", last_name="Sundberg")
    print(f"Found {len(students)} students:")
    for student in students:
        print(f"  - {student.full_name} (personID={student.person_id})")
        # Username isn't on search rows — resolve from the profile lazily.
        try:
            print(f"    SU username: {student.get_username(daisy)}")
        except AmbiguousMatchError as e:
            print(f"    no username available: {e}")
        if student.email:
            print(f"    Email: {student.email}")

    # Course iteration for an entire semester
    print("\n3. Listing courses for VT2026 and one course's medverkande...")
    vt2026 = Semester.from_label("VT2026")
    courses = daisy.get_courses(vt2026)
    print(f"  {len(courses)} courses for {vt2026}")
    for course in courses[:3]:
        print(
            f"    {course.beteckning:14s} {course.name[:45]:45s} "
            f"{course.ects} hp  {course.start_date} → {course.end_date}"
        )

    # Drill into the first course's role-grouped participants
    first = courses[0]
    print(f"\n  Medverkande on {first.beteckning} {first.name}:")
    for cs in daisy.get_course_participants(first.momenttillf_id):
        roles = ", ".join(cs.roles)
        # person_id is None for plain-text names (typically student-handledare).
        try:
            pid = cs.get_person_id(daisy)
        except AmbiguousMatchError as e:
            print(f"    ! {cs.name} ({roles}) — unresolved: {e}")
            continue
        print(f"    {cs.name:30s} [{roles}]  personID={pid}")

    print("\n=== Done ===")
