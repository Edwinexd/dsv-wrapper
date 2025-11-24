"""Example: Using ACT Lab client for digital signage management."""

from pathlib import Path

from dsv_wrapper import ACTLabClient

# Initialize the ACT Lab client
USERNAME = "your_username"
PASSWORD = "your_password"

with ACTLabClient(username=USERNAME, password=PASSWORD) as actlab:
    print("=== ACT Lab Client Example ===\n")

    # Get list of all slides
    print("1. Getting all slides...")
    slides = actlab.get_slides()
    print(f"Found {len(slides)} slides:")

    for slide in slides[:5]:  # Show first 5 slides
        print(f"  - ID: {slide.id}, Name: {slide.name}")

    # Upload a new slide
    print("\n2. Uploading a new slide...")
    slide_path = Path("path/to/your/slide.png")

    # Commented out to avoid accidental upload
    # if slide_path.exists():
    #     result = actlab.upload_slide(
    #         file_path=slide_path,
    #         slide_name="My New Slide",
    #         auto_delete=True
    #     )
    #
    #     if result.success:
    #         print(f"Upload successful! Slide ID: {result.slide_id}")
    #
    #         # Add the slide to show (ID 1 = Labbet)
    #         actlab.add_slide_to_show(result.slide_id, show_id="1")
    #         print(f"Slide added to show")
    #     else:
    #         print(f"Upload failed: {result.message}")
    # else:
    #     print(f"Slide file not found: {slide_path}")

    print("(Upload commented out to avoid accidental changes)")

    # Remove old slides, keeping only the latest N
    print("\n3. Cleaning up old slides...")
    # Commented out to avoid accidental deletion
    # removed_count = actlab.cleanup_old_slides(show_id="1", keep_latest=1)
    # print(f"Removed {removed_count} old slides")
    print("(Cleanup commented out to avoid accidental deletion)")

    # Managing slides manually
    print("\n4. Manual slide management...")

    # Add a slide to a show
    # actlab.add_slide_to_show(slide_id="123", show_id="1")

    # Remove a slide from a show
    # actlab.remove_slide_from_show(slide_id="123", show_id="1")

    print("Use add_slide_to_show() and remove_slide_from_show() for manual management")

    # Example workflow: Upload + Add + Cleanup
    print("\n5. Complete workflow example:")
    print("""
    # Complete workflow:
    result = actlab.upload_slide("slide.png", "New Map", auto_delete=True)
    if result.success:
        actlab.add_slide_to_show(result.slide_id, "1")
        actlab.cleanup_old_slides("1", keep_latest=1)
        print("Slide uploaded, added to show, and old slides removed!")
    """)

    print("\n=== Done ===")
