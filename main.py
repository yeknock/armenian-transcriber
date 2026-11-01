"""Live Armenian transcription -> English translation in the terminal, labelled by speaker (the challenge brief).

Your microphone is "Me"; the other side of the call (BlackHole) is "Speaker 1", "Speaker 2", ... Run from the repo root:
    python main.py --list-devices
    python main.py --mic "MacBook Air Microphone" --call BlackHole
Device names can be any unique part of the name, or the id from --list-devices. Ctrl+C stops: the phrases already
heard are still printed, then a latency summary. A second Ctrl+C stops at once.
Setup (README): the call app's speaker must be the Multi-Output Device "Call Output" (BlackHole + headphones).
"""
import argparse
import signal
import threading
import time

from transcriber.audio import list_input_devices, resolve_device


def load(name: str, make):
    print(f"Loading {name}...", end=" ", flush=True)
    started = time.perf_counter()
    model = make()
    print(f"{time.perf_counter() - started:.1f} s", flush=True)
    return model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--list-devices", action="store_true", help="print the input devices and exit")
    parser.add_argument("--mic", help="your microphone: part of its name or its id")
    parser.add_argument("--call", help="the call audio, BlackHole: part of its name or its id")
    args = parser.parse_args()
    if args.list_devices:
        print(list_input_devices())
        return
    if not args.mic or not args.call:
        parser.error("--mic and --call are both needed (see --list-devices)")
    try:
        mic, call = resolve_device(args.mic), resolve_device(args.call)
    except ValueError as error:
        raise SystemExit(f"error: {error}")

    from transcriber.asr import Transcriber            # imported here: --list-devices stays fast
    from transcriber.mt import Translator
    from transcriber.pipeline import MicrophoneSilent, Pipeline
    from transcriber.speakers import SpeakerIdentifier
    transcriber = load("speech recognition (first start after an install ~70 s, later ~10 s)", Transcriber)
    speakers = load("speaker identification", SpeakerIdentifier)
    translator = load("translation", Translator)
    try:
        pipeline = Pipeline(mic, call, transcriber, speakers, translator)
    except ValueError as error:
        raise SystemExit(f"error: {error}")

    # Ctrl+C only sets a flag, so it never interrupts the VAD in the middle of a chunk; the pipeline then finishes
    # the phrases already heard. After the first Ctrl+C the default handler is back: a second one stops at once.
    stop = threading.Event()

    def on_ctrl_c(signum, frame) -> None:
        stop.set()
        signal.signal(signal.SIGINT, signal.default_int_handler)
        print("\nStopping: finishing the last phrases...", flush=True)

    signal.signal(signal.SIGINT, on_ctrl_c)
    print("\nListening. Me = your microphone, Speaker 1, 2, ... = the call. Ctrl+C stops.\n", flush=True)
    try:
        pipeline.run(stop)
    except MicrophoneSilent as error:
        raise SystemExit(f"error: {error}")
    print(pipeline.summary())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:              # Ctrl+C while loading, or a second Ctrl+C
        raise SystemExit("\nStopped.")
