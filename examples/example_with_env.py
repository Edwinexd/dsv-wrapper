"""Example: Using environment variables for credentials."""

import os
from datetime import date

from dotenv import load_dotenv

from dsv_wrapper import DSVClient
from dsv_wrapper.models import RoomCategory

# Load environment variables from .env file
load_dotenv()

# Get credentials from environment
USERNAME = os.getenv("SU_USERNAME")
PASSWORD = os.getenv("SU_PASSWORD")

if not USERNAME or not PASSWORD:
    print("Error: SU_USERNAME and SU_PASSWORD environment variables must be set")
    print("\nCreate a .env file with:")
    print("SU_USERNAME=your_username")
    print("SU_PASSWORD=your_password")
    exit(1)

with DSVClient(username=USERNAME, password=PASSWORD) as client:
    print("=== Using Environment Variables ===\n")
    print(f"Authenticated as: {USERNAME}\n")

    # Use Daisy
    print("1. Getting room schedule...")
    daisy = client.daisy
    schedule = daisy.get_schedule(RoomCategory.GROUPA, date.today())
    print(f"Found {len(schedule.rooms)} rooms")

    # Use Handledning
    print("\n2. Getting teacher sessions...")
    handledning = client.handledning
    sessions = handledning.get_teacher_sessions()
    print(f"Found {len(sessions)} sessions")

    print("\n=== Done ===")
