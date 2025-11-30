#!/usr/bin/env python3
"""Example usage of MailClient with custom display name.

This example demonstrates:
1. Sending email with a custom sender display name
2. Reading emails from inbox
3. Using both sync and async clients
"""

import asyncio
import os

from dotenv import load_dotenv

from dsv_wrapper import AsyncMailClient, BodyType, MailClient

# Load environment variables from .env file
load_dotenv(override=True)


def sync_example():
    """Synchronous mail client example."""
    print("=== Sync Mail Client Example ===\n")

    # Option 1: Use environment variables
    # Set SU_USERNAME, SU_PASSWORD, SU_EMAIL, and SU_EMAIL_NAME in .env
    with MailClient() as client:
        # Get inbox info
        inbox = client.get_folder("inbox")
        print(f"Inbox: {inbox.total_count} total, {inbox.unread_count} unread\n")

        # List recent emails
        emails = client.get_emails("inbox", limit=3)
        print(f"Recent {len(emails)} emails:")
        for email in emails:
            print(f"  - {email.subject}")
            print(f"    From: {email.sender.name if email.sender else 'Unknown'}")
            print()

    # Option 2: Explicit parameters with custom display name
    with MailClient(
        username=os.getenv("SU_USERNAME"),
        password=os.getenv("SU_PASSWORD"),
        email_address=os.getenv("SU_EMAIL"),
        email_name="Lambda DSV",  # Custom display name
    ) as client:
        # Send email with custom display name
        result = client.send_email(
            to="recipient@example.com",
            subject="Test from Lambda DSV",
            body="This email is from Lambda DSV bot.",
            body_type=BodyType.TEXT,
        )
        if result.success:
            print(f"Email sent successfully! Message ID: {result.message_id}")
        else:
            print(f"Failed to send: {result.error}")


async def async_example():
    """Asynchronous mail client example."""
    print("\n=== Async Mail Client Example ===\n")

    # Both formats are supported for email_name:
    # 1. Plain name: "Lambda DSV"
    # 2. Name with email (validated): "Lambda DSV <lambda@dsv.su.se>"

    async with AsyncMailClient(email_name="Lambda DSV") as client:
        # Get inbox info
        inbox = await client.get_folder("inbox")
        print(f"Inbox: {inbox.total_count} total, {inbox.unread_count} unread\n")

        # List recent emails
        emails = await client.get_emails("inbox", limit=3)
        print(f"Recent {len(emails)} emails:")
        for email in emails:
            print(f"  - {email.subject}")
            print(f"    From: {email.sender.name if email.sender else 'Unknown'}")
            print()


if __name__ == "__main__":
    # Run sync example
    sync_example()

    # Run async example
    asyncio.run(async_example())
