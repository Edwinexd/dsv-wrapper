#!/usr/bin/env python3
"""Debug what's in the show"""
import os
from dotenv import load_dotenv

load_dotenv()

from dsv_wrapper import ACTLabClient

with ACTLabClient() as actlab:
    actlab._ensure_authenticated()

    # Get the page
    response = actlab.session.get("https://www2.dsv.su.se/act-lab/admin/")

    from dsv_wrapper.utils import parse_html
    soup = parse_html(response.text)

    # Find show 1
    show_div = soup.find("div", {"id": "1", "class": "show"})

    if show_div:
        print("Found show 1")

        # Get all slides in the show
        slide_divs = show_div.find_all("div", class_="slide")
        print(f"\nSlides in show 1: {len(slide_divs)}")

        for slide_div in slide_divs:
            slide_id = slide_div.get("id")

            # Try to find slide name or other identifying info
            name_elem = slide_div.find(class_="slide-name")
            if name_elem:
                name = name_elem.get_text(strip=True)
            else:
                name = "No name"

            print(f"  - Slide ID: {slide_id}, Name: {name}")

            # Check if there's an image
            img = slide_div.find("img", class_="slideimg")
            if img:
                src = img.get("src")
                print(f"    Image src: {src}")
    else:
        print("Show 1 not found!")

        # List all shows
        shows_div = soup.find("div", {"id": "shows"})
        if shows_div:
            show_divs = shows_div.find_all("div", class_="show")
            print(f"\nAll shows found: {len(show_divs)}")
            for show in show_divs:
                print(f"  - Show ID: {show.get('id')}")
