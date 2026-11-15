"""Upload game CSVs and save a QR PNG. Run --help for examples."""
import argparse
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    parser.add_argument("timeline", type=Path, nargs="?")
    parser.add_argument("--server", default="http://127.0.0.1:8000")
    parser.add_argument("--qr", type=Path, default=Path("game-run-qr.png"))
    args = parser.parse_args()
    files = {"summary": (args.summary.name, args.summary.read_bytes(), "text/csv")}
    if args.timeline:
        files["timeline"] = (args.timeline.name, args.timeline.read_bytes(), "text/csv")
    base = args.server.rstrip("/")
    # LAN uploads should not accidentally travel through a shell's proxy.
    with httpx.Client(timeout=30, trust_env=False) as client:
        response = client.post(base+"/runs", files=files)
        if response.is_error:
            raise SystemExit(f"Upload failed (HTTP {response.status_code}): {response.text}")
        result = response.json()
        qr = client.get(base+result["qr_path"])
        qr.raise_for_status()
        args.qr.write_bytes(qr.content)
    print("Run ID:", result["runId"])
    print("QR payload:", result["qr_payload"])
    print("QR image:", args.qr.resolve())
    print("Scan that image, or paste the payload into Load game QR in the miniapp.")


if __name__ == "__main__":
    main()
