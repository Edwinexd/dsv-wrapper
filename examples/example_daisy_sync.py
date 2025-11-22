"""Example: Using Daisy client synchronously."""

from datetime import date, time

from dsv_wrapper import DaisyClient, RoomCategory

# Initialize the Daisy client
USERNAME = "your_username"
PASSWORD = "your_password"

with DaisyClient(username=USERNAME, password=PASSWORD, service="daisy_staff") as daisy:
    print("=== Daisy Client Example ===\n")

    # Get room schedule for today
    print("1. Getting room schedule for GROUPA...")
    schedule = daisy.get_schedule(RoomCategory.GROUPA, date.today())
    print(f"Found {len(schedule.rooms)} rooms on {schedule.date}")

    # Display available time slots
    print("\nAvailable time slots:")
    for room in schedule.rooms:
        print(f"\n  {room.name} ({room.category.value})")
        available_slots = [slot for slot in room.available_times if slot.available]

        if available_slots:
            for slot in available_slots[:3]:  # Show first 3 available slots
                print(f"    {slot.start} - {slot.end}")
        else:
            print("    No available slots")

    # Search for students
    print("\n2. Searching for students...")
    students = daisy.search_students("john", limit=5)
    print(f"Found {len(students)} students:")

    for student in students:
        print(f"  - {student.full_name} ({student.username})")
        if student.email:
            print(f"    Email: {student.email}")
        if student.program:
            print(f"    Program: {student.program}")

    # Get room activities (scheduled events)
    print("\n3. Getting room activities...")
    if schedule.rooms:
        room_id = schedule.rooms[0].id
        activities = daisy.get_room_activities(room_id, date.today())
        print(f"Activities in {room_id}: {len(activities)}")

        for activity in activities:
            print(f"  - {activity.start_time} - {activity.end_time}")
            if activity.course_code:
                print(f"    Course: {activity.course_code} - {activity.course_name}")

    # Example: Book a room (commented out to avoid accidental booking)
    # print("\n4. Booking a room...")
    # try:
    #     success = daisy.book_room(
    #         room_id=schedule.rooms[0].id,
    #         schedule_date=date.today(),
    #         start_time=time(14, 0),
    #         end_time=time(15, 0),
    #         purpose="Team meeting"
    #     )
    #     if success:
    #         print("Room booked successfully!")
    # except RoomNotAvailableError:
    #     print("Room is not available for the requested time")
    # except BookingError as e:
    #     print(f"Booking failed: {e}")

    print("\n=== Done ===")
