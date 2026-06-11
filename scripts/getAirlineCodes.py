#!/usr/bin/env python3
"""Fetch the airline codes table from Wikipedia and write it to a CSV file."""

import io
import sys
import requests
import pandas as pd

URL = "https://en.wikipedia.org/wiki/List_of_airline_codes"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}


def fetch_airline_codes(output_path):
    response = requests.get(URL, headers=HEADERS, timeout=30)
    if not response.ok:
        print(f"ERROR: failed to fetch '{URL}' (status {response.status_code})")
        sys.exit(1)

    df = pd.read_html(io.StringIO(response.text))[0]
    df.to_csv(output_path, index=False)
    print(f"Wrote {len(df)} rows to {output_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <output.csv>")
        sys.exit(1)
    fetch_airline_codes(sys.argv[1])
