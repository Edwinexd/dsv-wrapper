"""Example: Using async clients."""

import asyncio
from datetime import date

from dsv_wrapper import AsyncDSVClient
from dsv_wrapper.models import RoomCategory


async def main():
    """Main async function."""
    USERNAME = "your_username"
    PASSWORD = "your_password"

    async with AsyncDSVClient(username=USERNAME, password=PASSWORD) as client:
        print("=== Async DSVClient Example ===\n")

        # Get Daisy client
        print("1. Getting async Daisy client...")
        daisy = await client.get_daisy()

        # Get room schedule
        print("2. Fetching room schedule...")
        schedule = await daisy.get_schedule(RoomCategory.GROUPA, date.today())
        print(f"Found {len(schedule.rooms)} rooms in GROUPA")

        for room in schedule.rooms[:3]:  # Show first 3 rooms
            available = [slot for slot in room.available_times if slot.available]
            print(f"  {room.name}: {len(available)} available slots")

        # Search students
        print("\n3. Searching for students...")
        students = await daisy.search_students("maria", limit=5)
        print(f"Found {len(students)} students:")

        for student in students:
            print(f"  - {student.full_name} ({student.username})")

        # Get Handledning client
        print("\n4. Getting async Handledning client...")
        handledning = await client.get_handledning()

        # Get teacher sessions
        print("5. Fetching teacher sessions...")
        sessions = await handledning.get_teacher_sessions()
        print(f"Found {len(sessions)} sessions")

        for session in sessions:
            print(f"  - {session.course_code}: {session.course_name}")

        # Parallel operations example
        print("\n6. Running parallel operations...")

        # Run multiple operations concurrently
        results = await asyncio.gather(
            daisy.search_students("john", limit=3),
            daisy.search_students("anna", limit=3),
            handledning.get_all_active_sessions(),
            return_exceptions=True,
        )

        john_students, anna_students, active_sessions = results

        if not isinstance(john_students, Exception):
            print(f"Found {len(john_students)} students named John")
        if not isinstance(anna_students, Exception):
            print(f"Found {len(anna_students)} students named Anna")
        if not isinstance(active_sessions, Exception):
            print(f"Found {len(active_sessions)} active sessions")

        print("\n=== Done ===")


if __name__ == "__main__":
    asyncio.run(main())
