"""Example: Using Handledning client synchronously."""

from dsv_wrapper import HandledningClient

# Initialize the Handledning client
USERNAME = "your_username"
PASSWORD = "your_password"

with HandledningClient(username=USERNAME, password=PASSWORD) as handledning:
    print("=== Handledning Client Example ===\n")

    # Get teacher sessions
    print("1. Getting teacher sessions...")
    sessions = handledning.get_teacher_sessions()
    print(f"Found {len(sessions)} sessions")

    for session in sessions:
        print(f"\n  Course: {session.course_code} - {session.course_name}")
        print(f"  Time: {session.start_time} - {session.end_time}")
        print(f"  Room: {session.room or 'N/A'}")
        print(f"  Status: {'Active' if session.is_active else 'Inactive'}")
        print(f"  Teacher: {session.teacher.username}")

    # Get all active sessions
    print("\n2. Getting all active sessions...")
    active_sessions = handledning.get_all_active_sessions()
    print(f"Found {len(active_sessions)} active sessions")

    for session in active_sessions:
        print(f"  - {session.course_code}: {session.course_name}")

    # Get queue for a session (example)
    if sessions:
        print("\n3. Getting queue for first session...")
        session_id = "example_session_id"  # Replace with actual session ID

        # This would fail without a valid session_id, so commenting out
        # queue = handledning.get_queue(session_id)
        # print(f"Queue length: {len(queue)}")
        #
        # for entry in queue:
        #     print(f"  {entry.position}. {entry.student.username}")
        #     print(f"     Status: {entry.status.value}")
        #     print(f"     Time: {entry.timestamp.strftime('%H:%M')}")
        #     if entry.room:
        #         print(f"     Room: {entry.room}")

        print("(Skipped - requires valid session ID)")

    # Example: Add to queue (student)
    print("\n4. Adding to queue...")
    # session_id = "example_session_id"  # Replace with actual session ID
    # try:
    #     success = handledning.add_to_queue(session_id)
    #     if success:
    #         print("Added to queue successfully!")
    # except QueueError as e:
    #     print(f"Failed to add to queue: {e}")
    print("(Commented out to avoid accidental queue modification)")

    # Example: Activate session (teacher only)
    print("\n5. Activating session...")
    # session_id = "example_session_id"  # Replace with actual session ID
    # try:
    #     success = handledning.activate_session(session_id)
    #     if success:
    #         print("Session activated successfully!")
    # except HandledningError as e:
    #     print(f"Failed to activate session: {e}")
    print("(Commented out to avoid accidental session modification)")

    # Example: Remove from queue (teacher)
    print("\n6. Removing from queue...")
    # session_id = "example_session_id"  # Replace with actual session ID
    # student_username = "student_username"
    # try:
    #     success = handledning.remove_from_queue(session_id, student_username)
    #     if success:
    #         print(f"Removed {student_username} from queue!")
    # except QueueError as e:
    #     print(f"Failed to remove from queue: {e}")
    print("(Commented out to avoid accidental queue modification)")

    print("\n=== Done ===")
