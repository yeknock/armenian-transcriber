"""Live level meter for two input devices: microphone + call audio (BlackHole).

Milestone M0 check: proves that both audio inputs reach Python, independently.

Usage:
    python scripts/level_meter.py --list
    python scripts/level_meter.py --mic <device id> --call <device id>
"""
import argparse
import time

import numpy as np
import sounddevice as sd

BAR_WIDTH = 30
FLOOR_DB = -60.0          # quieter than this is drawn as an empty bar
SILENCE_CHECK_AFTER_S = 3.0


class Meter:
    """Opens one input device and keeps its latest loudness (RMS in dBFS)."""

    def __init__(self, label: str, device: int):
        info = sd.query_devices(device)  # raises if the id does not exist
        if info["max_input_channels"] < 1:
            raise SystemExit(f"Device {device} ({info['name']}) has no input channels.")
        self.label = label
        self.device_name = info["name"]
        self.samplerate = int(info["default_samplerate"])
        self.channels = min(2, info["max_input_channels"])
        self.rms_db = -np.inf
        self.peak = 0.0          # loudest sample seen since start
        self.dropouts = 0        # callbacks that reported overflow/underflow
        self.stream = sd.InputStream(
            device=device,
            channels=self.channels,
            samplerate=self.samplerate,
            dtype="float32",
            callback=self._callback,
        )

    def _callback(self, indata, frames, time_info, status):
        # Runs on the audio thread. A meter only needs two numbers, so this is cheap.
        if status:
            self.dropouts += 1
        rms = float(np.sqrt(np.mean(indata ** 2)))
        self.rms_db = 20 * np.log10(rms) if rms > 0 else -np.inf
        self.peak = max(self.peak, float(np.max(np.abs(indata))))

    def bar(self) -> str:
        level = (max(self.rms_db, FLOOR_DB) - FLOOR_DB) / -FLOOR_DB
        filled = int(round(level * BAR_WIDTH))
        db_text = "  -inf" if self.rms_db == -np.inf else f"{self.rms_db:6.1f}"
        return f"{self.label:<4} [{'#' * filled}{'.' * (BAR_WIDTH - filled)}] {db_text} dB"


def list_devices() -> None:
    print(sd.query_devices())
    print("\n'>' = default input, '<' = default output. Use the number on the left.")


def run(mic_id: int, call_id: int) -> None:
    meters = [Meter("MIC", mic_id), Meter("CALL", call_id)]
    for m in meters:
        print(f"{m.label}: '{m.device_name}' — {m.samplerate} Hz, {m.channels} ch")
    print("Speak → MIC should move. Play audio to the Multi-Output Device → CALL should move.")
    print("Ctrl+C to stop.\n")

    warned = set()
    start = time.monotonic()
    for m in meters:
        m.stream.start()
    try:
        while True:
            line = "   ".join(m.bar() for m in meters)
            drops = sum(m.dropouts for m in meters)
            print(f"\r{line}   dropouts: {drops}", end="", flush=True)

            # Digital silence (exact zeros) usually means a missing macOS Microphone
            # permission or wrong routing — say so once, clearly.
            if time.monotonic() - start > SILENCE_CHECK_AFTER_S:
                for m in meters:
                    if m.peak == 0.0 and m.label not in warned:
                        warned.add(m.label)
                        print(f"\n!! {m.label} has delivered only exact zeros. Check: "
                              f"System Settings → Privacy & Security → Microphone → allow your "
                              f"terminal app; and (for CALL) that audio is playing to the "
                              f"Multi-Output Device.")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print()
    finally:
        for m in meters:
            m.stream.stop()
            m.stream.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="list audio devices and exit")
    parser.add_argument("--mic", type=int, help="device id of the microphone")
    parser.add_argument("--call", type=int, help="device id of BlackHole (call audio)")
    args = parser.parse_args()

    if args.list:
        list_devices()
        return
    if args.mic is None or args.call is None:
        parser.error("give both --mic and --call (see --list for ids)")
    run(args.mic, args.call)


if __name__ == "__main__":
    main()
