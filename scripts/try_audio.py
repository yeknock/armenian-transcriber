"""Standalone checks for the audio module (briefs/audio.md).

Run from the repo root:
    python -m scripts.try_audio --list
    python -m scripts.try_audio --mic "MacBook Air Microphone" --call BlackHole
"""
import argparse

import sounddevice as sd

from transcriber.audio import list_input_devices, resolve_device


def describe(label: str, spec: str) -> None:
    device_id = resolve_device(spec)
    info = sd.query_devices(device_id)
    print(f"{label}: {spec!r} -> id {device_id} {info['name']!r}, "
          f"{info['max_input_channels']} input ch, {info['default_samplerate']:.0f} Hz")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="print the input devices and exit")
    parser.add_argument("--mic", help="microphone: device id or part of its name")
    parser.add_argument("--call", help="call audio (BlackHole): device id or part of its name")
    args = parser.parse_args()

    if args.list:
        print(list_input_devices())
        return
    if args.mic is None or args.call is None:
        parser.error("give --list, or both --mic and --call")
    try:
        describe("mic ", args.mic)
        describe("call", args.call)
    except ValueError as error:
        raise SystemExit(f"error: {error}")


if __name__ == "__main__":
    main()
