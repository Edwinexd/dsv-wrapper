"""Example async bot that monitors for emails with attachments.

This example demonstrates:
- Using AsyncMailBot for asynchronous email monitoring
- Filtering emails that contain attachments
- Downloading and displaying attachment metadata
- Reading .txt file attachments
- Running the bot with graceful shutdown
"""

import asyncio
import logging

from dsv_wrapper import AsyncMailBot, AsyncMailClient

# Enable logging to see bot activity
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


async def main():
    """Run the async bot to monitor for emails with attachments."""
    print("=== Async Email Bot - Attachment Monitor ===\n")
    print("Monitoring inbox for emails with attachments...")
    print("Will download and display .txt file contents")
    print("Press Ctrl+C to stop\n")

    # Create a shared mail client for downloading attachments
    # This avoids creating a new connection for each email
    mail_client = AsyncMailClient()
    await mail_client.__aenter__()

    def handle_email_with_attachment(event):
        """Handle emails that have attachments.

        Note: Bot callbacks are called from a thread, so we need to create
        a new event loop to run async code.
        """
        email = event.email

        # Check if email has attachments
        if not email.has_attachments:
            return  # Skip emails without attachments

        # Print email details
        print("\n📎 Email with attachment detected!")
        print(f"   Subject: {email.subject}")
        print(f"   From: {email.sender.name} <{email.sender.email}>")
        print(f"   Received: {email.received_at}")

        # Print body preview if available
        if email.body:
            body_preview = email.body[:150].replace("\n", " ")
            print(f"   Body: {body_preview}...")

        # Get full email to see attachments
        # Note: Bot emails only have has_attachments flag,
        # need to fetch full email for attachment details
        async def _get_full_email():
            return await mail_client.get_email(email.id, email.change_key)

        try:
            full_email = asyncio.run(_get_full_email())
            print(f"   Attachments ({len(full_email.attachments)}):")

            for att in full_email.attachments:
                print(f"     - {att.filename} ({att.size} bytes, {att.content_type})")

                # Download and print .txt file contents
                if att.filename.endswith(".txt"):
                    try:
                        # Run async download in new event loop
                        # Using the shared mail_client to avoid creating new connections
                        filename = att.filename  # Bind loop variable for closure

                        async def _download(fname=filename):
                            return await mail_client.download_attachment(
                                full_email.change_key, fname
                            )

                        data = asyncio.run(_download())
                        content = data.decode("utf-8", errors="replace")
                        print(f"\n     📄 Contents of {att.filename}:")
                        print("     " + "-" * 60)
                        for line in content.split("\n")[:20]:  # First 20 lines
                            print(f"     {line}")
                        if len(content.split("\n")) > 20:
                            print(f"     ... ({len(content.split('\n')) - 20} more lines)")
                        print("     " + "-" * 60)
                    except (OSError, UnicodeDecodeError, ValueError) as e:
                        print(f"     ⚠️  Error reading {att.filename}: {e}")
        except (OSError, ValueError) as e:
            print(f"   ⚠️  Error getting full email: {e}")

        print()

    def handle_error(error):
        """Handle bot errors."""
        print(f"\n⚠️  Bot error: {error.message}")
        if not error.recoverable:
            print("   Fatal error - bot will stop")

    try:
        # Create and run the async bot
        async with AsyncMailBot(
            folder="inbox",  # Monitor inbox
            fetch_limit=20,  # Check last 20 emails on each notification
            poll_interval=60,  # Poll every 60s if IDLE not available
        ) as bot:
            # Register callbacks
            bot.on_new_email(handle_email_with_attachment)
            bot.on_error(handle_error)

            # Start monitoring (this will block)
            try:
                await bot.start()
            except KeyboardInterrupt:
                print("\n\nStopping async bot...")
                await bot.stop()

        print("Async bot stopped gracefully")
    finally:
        # Clean up shared mail client
        await mail_client.__aexit__(None, None, None)


if __name__ == "__main__":
    # Run the async bot
    asyncio.run(main())
