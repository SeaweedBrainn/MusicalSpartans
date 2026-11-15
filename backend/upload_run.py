"""Uploads a game run to the backend, the same way the game should.

Usage:  python upload_run.py <summary.csv> <timeline.csv> [backend_url]
Example: python upload_run.py ../app/src/main/assets/song10-chart1-summary.csv ../app/src/main/assets/song10-chart1.csv
"""

import sys
from pathlib import Path

import httpx


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    summary, timeline = Path(sys.argv[1]), Path(sys.argv[2])
    url = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:8000"

    with summary.open("rb") as s, timeline.open("rb") as t:
        response = httpx.post(f"{url}/runs", files={"summary": (summary.name, s), "timeline": (timeline.name, t)})
    response.raise_for_status()
    print("Uploaded. Run ID:", response.json()["runId"])


if __name__ == "__main__":
    main()
