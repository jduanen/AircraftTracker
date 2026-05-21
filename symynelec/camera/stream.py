#!/usr/bin/env python3
"""Probe common RTSP URL patterns for the Symynelec SN-P6-B and open the stream in VLC."""

import argparse
import subprocess
import sys

RTSP_PATHS = [
    "/onvif1",
    "/stream1",
    "/live/ch00_0",
    "/h264Preview_01_main",
    "/live",
    "/cam/realmonitor?channel=1&subtype=0",
    "/videoMain",
    "/Streaming/Channels/101",
    "/video.h264",
]


def probe(url: str) -> bool:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-rtsp_transport", "tcp", "-i", url],
        timeout=4,
        capture_output=True,
    )
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Open Symynelec camera stream in VLC")
    parser.add_argument("--ip", required=True, help="Camera IP address")
    parser.add_argument("--user", required=True, help="Camera username")
    parser.add_argument("--password", required=True, help="Camera password")
    args = parser.parse_args()

    tried = []
    for path in RTSP_PATHS:
        url = f"rtsp://{args.user}:{args.password}@{args.ip}:554{path}"
        tried.append(url)
        print(f"Trying {url} ...", end=" ", flush=True)
        try:
            if probe(url):
                print("OK")
                print(f"\nWorking URL: {url}")
                subprocess.run(["vlc", url])
                return
            else:
                print("no response")
        except subprocess.TimeoutExpired:
            print("timed out")
        except FileNotFoundError as e:
            sys.exit(f"Missing dependency: {e.filename} — run: sudo apt install ffmpeg vlc")

    print("\nNo RTSP URL responded. Tried:")
    for u in tried:
        print(f"  {u}")
    print("\nTo find the correct URL, capture traffic from the Android app with Wireshark.")


if __name__ == "__main__":
    main()
