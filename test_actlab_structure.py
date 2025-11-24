#!/usr/bin/env python3
"""Test ACT Lab HTML structure"""
import os
from dotenv import load_dotenv

load_dotenv()

from dsv_wrapper import ACTLabClient

with ACTLabClient() as actlab:
    actlab._ensure_authenticated()

    response = actlab.session.get("https://www2.dsv.su.se/act-lab/admin/")

    from dsv_wrapper.utils import parse_html
    soup = parse_html(response.text)

    # Find all slides
    slides = soup.find_all("div", class_="slide")
    print(f"Found {len(slides)} slides\n")

    # Show first 3 slides structure
    for i, slide in enumerate(slides[:3]):
        print(f"Slide {i+1}:")
        print(f"  ID attribute: {slide.get('id')}")
        print(f"  All attributes: {slide.attrs}")

        # Look for any input with slideid
        slideid_input = slide.find("input", {"name": "slideid"})
        if slideid_input:
            print(f"  Found slideid input: {slideid_input.get('value')}")
        print()

    # Check show structure
    print("\n" + "="*60)
    shows_div = soup.find("div", {"id": "shows"})
    if shows_div:
        show_divs = shows_div.find_all("div", class_="show")
        print(f"Found {len(show_divs)} shows")
        for show in show_divs:
            print(f"  Show ID: {show.get('id')}")
