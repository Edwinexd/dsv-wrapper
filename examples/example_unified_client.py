"""Example: Using the unified DSVClient."""

from datetime import date

from dsv_wrapper import DSVClient
from dsv_wrapper.models import RoomCategory

# Initialize the unified client
USERNAME = "your_username"
PASSWORD = "your_password"

with DSVClient(username=USERNAME, password=PASSWORD) as client:
    print("=== Unified DSVClient Example ===\n")

    # Access Daisy through the unified client
    print("1. Using Daisy client...")
    daisy = client.daisy

    # Get room schedule
    schedule = daisy.get_schedule(RoomCategory.BOOKABLE_GROUP_ROOMS, date.today())
    print(f"Schedule: {schedule.room_category_title}")
    print(f"Found {len(schedule.activities)} rooms")

    # Show activities
    total_activities = sum(len(activities) for activities in schedule.activities.values())
    print(f"Total activities: {total_activities}")

    # Search students
    students = daisy.search_students("anna", limit=5)
    print(f"Found {len(students)} students matching 'anna'")

    # Access Handledning through the unified client
    print("\n2. Using Handledning client...")
    handledning = client.handledning

    # Get teacher sessions
    sessions = handledning.get_teacher_sessions()
    print(f"Found {len(sessions)} teacher sessions")

    for session in sessions:
        print(f"  - {session.course_code}: {session.course_name}")
        status = "Active" if session.is_active else "Inactive"
        print(f"    Status: {status}")

    # Get all active sessions
    active_sessions = handledning.get_all_active_sessions()
    print(f"\nTotal active sessions: {len(active_sessions)}")

    # Cross-service example: Find students and check their handledning sessions
    print("\n3. Cross-service operations...")
    if students:
        student = students[0]
        print(f"Checking sessions for student: {student.username}")

        # In a real scenario, you might want to check if this student
        # is in any handledning queues
        for session in active_sessions:
            print(f"  Session: {session.course_code} - {session.course_name}")
            # You could fetch the queue and check if student is in it
            # queue = handledning.get_queue(session_id)
            # if any(entry.student.username == student.username for entry in queue):
            #     print(f"    Student is in queue!")

    print("\n=== Done ===")
