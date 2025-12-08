"""Example of using the email monitoring bot.

This example demonstrates how to monitor an inbox for new emails
using IMAP IDLE (push notifications) with automatic fallback to polling.

Requirements:
- Set SU_USERNAME, SU_PASSWORD, and SU_EMAIL environment variables
- Or pass credentials directly to MailBot()
"""

import logging

from dsv_wrapper import AsyncMailBot, MailBot

# Enable logging to see bot activity
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


def sync_example():
    """Example using synchronous MailBot."""
    print("=== Synchronous MailBot Example ===\n")

    def handle_new_email(event):
        """Handle new email events."""
        email = event.email
        print("\n📧 New email detected!")
        print(f"Subject: {email.subject}")
        print(f"From: {email.sender.email}")
        print(f"Received: {email.received_datetime}")
        if email.body:
            print(f"Body preview: {email.body[:100]}...")
        print()

    def handle_error(error):
        """Handle bot errors."""
        print(f"\n⚠️  Bot error: {error.message}")
        if not error.recoverable:
            print("Fatal error - bot will stop")
        print()

    # Create bot with custom settings
    with MailBot(
        folder="inbox",  # Monitor inbox
        fetch_limit=10,  # Fetch 10 most recent emails on each check
        poll_interval=60,  # Poll every 60s if IDLE unavailable
        enable_polling_fallback=True,  # Auto-fallback to polling
    ) as bot:
        # Register event handlers
        bot.on_new_email(handle_new_email)
        bot.on_error(handle_error)

        print("Monitoring inbox for new emails...")
        print("Using IMAP IDLE (push) with polling fallback")
        print("Press Ctrl+C to stop\n")

        try:
            bot.start()  # Blocks until stopped
        except KeyboardInterrupt:
            print("\n\nStopping bot...")
            bot.stop()

    print("Bot stopped gracefully")


async def async_example():
    """Example using asynchronous AsyncMailBot."""

    print("\n\n=== Asynchronous AsyncMailBot Example ===\n")

    def handle_new_email(event):
        """Handle new email events (sync callback)."""
        email = event.email
        print(f"📧 {email.subject} (from {email.sender.email})")

    async with AsyncMailBot(fetch_limit=5) as bot:
        bot.on_new_email(handle_new_email)

        print("Async bot monitoring inbox...")
        print("Press Ctrl+C to stop\n")

        try:
            # Start monitoring (blocks)
            await bot.start()
        except KeyboardInterrupt:
            print("\n\nStopping async bot...")
            await bot.stop()

    print("Async bot stopped")


def monitoring_specific_folder_example():
    """Example monitoring a specific folder."""
    print("\n\n=== Monitor Specific Folder Example ===\n")

    with MailBot(folder="sent") as bot:  # Monitor sent items
        bot.on_new_email(lambda e: print(f"Sent item: {e.email.subject}"))

        print("Monitoring 'Sent Items' folder...")
        print("Press Ctrl+C to stop\n")

        try:
            bot.start()
        except KeyboardInterrupt:
            print("\nStopping...")
            bot.stop()


def multiple_callbacks_example():
    """Example with multiple event handlers."""
    print("\n\n=== Multiple Callbacks Example ===\n")

    # Track statistics
    email_count = {"count": 0}

    def log_email(event):
        """Log email to console."""
        print(f"📧 {event.email.subject}")

    def count_email(event):
        """Count emails."""
        email_count["count"] += 1
        print(f"   Total emails processed: {email_count['count']}")

    def filter_important(event):
        """Filter important emails."""
        if event.email.importance.value == "high":
            print("   ⚠️  HIGH IMPORTANCE!")

    with MailBot(fetch_limit=3) as bot:
        # Register multiple callbacks
        bot.on_new_email(log_email)
        bot.on_new_email(count_email)
        bot.on_new_email(filter_important)

        print("Monitoring with multiple callbacks...")
        print("Press Ctrl+C to stop\n")

        try:
            bot.start()
        except KeyboardInterrupt:
            print(f"\nStopping... (processed {email_count['count']} emails)")
            bot.stop()


if __name__ == "__main__":
    # Run the synchronous example
    sync_example()

    # Uncomment to run other examples:

    # import asyncio
    # asyncio.run(async_example())

    # monitoring_specific_folder_example()

    # multiple_callbacks_example()
