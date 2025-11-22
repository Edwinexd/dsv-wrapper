"""Example: Using Daisy client synchronously."""

from datetime import date, time

from dsv_wrapper import DaisyClient, RoomCategory

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
                print(f"    {activity.time_slot_start.to_string()} - {activity.time_slot_end.to_string()}: {activity.event}")
        else:
            print("    No activities")

    # Search for students
    print("\n2. Searching for students...")
    students = daisy.search_students("john", limit=5)
    print(f"Found {len(students)} students:")

    for student in students:
        first_name = student.first_name or ""
        last_name = student.last_name or ""
        full_name = f"{first_name} {last_name}".strip()
        print(f"  - {full_name} ({student.username})")
        if student.email:
            print(f"    Email: {student.email}")
        if student.program:
            print(f"    Program: {student.program}")

    print("\n=== Done ===")
