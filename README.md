# Armenian live transcriber

A Python program for the terminal that listens to a live call, writes down what is said in **Armenian**, translates
it into **English** and shows who said it, within a few seconds of the end of each phrase. Everything runs **locally**
on a MacBook Air M1 with 8 GB of memory: no cloud speech or translation services.

```
[00:01:12] Speaker 1
  HY: Բարև, ինչպե՞ս ես։
  EN: Hi, how are you?

[00:01:15] Me
  HY: Լավ եմ, շնորհակալություն։
  EN: I'm fine, thank you.
```

Your microphone is always `Me`. The other side of the call (whatever the call app plays) is told apart by voice as
`Speaker 1`, `Speaker 2`, …, and a person keeps their label for the whole session.

This is a coding challenge (Mathrix AI, October 2026). How it was built — plan, decisions with numbers, tests and the
full AI chat history — is part of the result; see [How this was built](#how-this-was-built).

---

## Contents

1. [Status against the brief](#status-against-the-brief)
2. [What you need](#what-you-need)
3. [Setup](#setup)
4. [Running it](#running-it)
5. [How it works](#how-it-works)
6. [Models: what I chose and why](#models-what-i-chose-and-why)
7. [Measured results](#measured-results)
8. [Known limitations](#known-limitations)
9. [What I would improve with more time](#what-i-would-improve-with-more-time)
10. [Repository layout](#repository-layout)
11. [Tools and tests](#tools-and-tests)
12. [How this was built](#how-this-was-built)
13. [Licences](#licences)

---

## Status against the brief

| Brief requirement | Status |
|---|---|
| Capture the microphone and the system audio (the call) at the same time; user picks the devices | ✅ `--list-devices`, `--mic`, `--call` (device name or id) |
| Armenian speech → Armenian text | ✅ NVIDIA FastConformer (CER 8.8 %, WER 26.7 % on our own spontaneous recordings) |
| Translate every segment into English | ✅ NLLB-200 1.3B with a spoken→written Armenian word list (600M with `--mt-model nllb-600m`) |
| Mic = `Me`; call side = `Speaker 1, 2, …`, stable for the session | ✅ `Me` always right. ⚠️ Call-side labels: tuned on a 2-voice podcast after a live call gave 7 labels for 3 people; the next 6-minute call with 3 people found 3 (whether every phrase went to the right person was not checked; see [limitations](#known-limitations)) |
| Live terminal output: time, speaker, Armenian, English | ✅ |
| At most 5 s from the end of a phrase to its English line | ✅ measured in live calls: 0 phrases over 5 s; the longest run with the final settings (6.3 min, 81 entries) peaked at 4.64 s |
| Local models only, Python, runs on my own laptop | ✅ MacBook Air M1, 8 GB, macOS, Python 3.12 |
| README: setup, models and alternatives, architecture, limitations | ✅ this file |
| Full AI chat transcripts in `chats/` | ⚠️ one Markdown file per session; for sessions 04–07 a full export could not be made (the app's export failed, and for 07 the transcript file was not available), so those files are detailed handovers; the original chats are in the app (see [How this was built](#how-this-was-built)) |
| No model weights, audio or keys in Git | ✅ `.gitignore`; checked with `git ls-files` |

Detailed checks with dates and evidence: [`TESTS.md`](TESTS.md).

---

## What you need

- **A Mac.** Developed and tested on a **MacBook Air M1, 8 GB**, macOS 26. Other systems need a different way to
  capture the call audio (see [Setup step 3](#3-route-the-call-audio-blackhole--multi-output-device)); the Python code
  itself is not Mac-specific.
- **Python 3.12** (3.12.3 used) and **Homebrew** (for BlackHole).
- **Headphones** for listening to the call — wired is safest; Bluetooth works **only for listening** (see below).
- **About 4 GB of disk:** ~1.9 GB for the Python environment (PyTorch, NeMo, …) and ~1.9 GB for the three models,
  plus temporarily ~5.5 GB while the translation model is downloaded and converted.
- **Internet once**, to install the packages and download the models. After that it runs offline.
- **Free memory:** the program uses roughly 3 GB with the default models. On an 8 GB Mac, close what you don't need
  besides the call app.

---

## Setup

All commands run from the repository folder.

### 1. Python environment

```
git clone https://github.com/yeknock/armenian-transcriber.git
cd armenian-transcriber
python3 -m venv .venv
source .venv/bin/activate          # in every new terminal window
pip install -r requirements.txt
```

`nemo_toolkit[asr]` brings PyTorch and many other packages, so this takes a while. The pinned versions are the ones
measured here (`silero-vad==6.2.3`, `nemo_toolkit==3.0.0`, `ctranslate2==4.8.4`, `jiwer==4.0.0`); the others were
torch 2.15.0, transformers 5.22.1, onnxruntime 1.31.1, numpy 2.5.4, sounddevice 0.5.6, soxr 1.1.0.

### 2. Download the models (once)

Every model lives in the git-ignored `models/` folder and is loaded only from there; nothing is fetched while the
program runs. If one is missing, the program stops and prints the exact command below.

```
# speech recognition: NVIDIA FastConformer, Armenian (~440 MB)
hf download nvidia/stt_hy_fastconformer_hybrid_large_pc --local-dir models/nvidia_hy_nemo

# speaker identification: NVIDIA TitaNet-Large (~100 MB)
hf download nvidia/speakerverification_en_titanet_large --local-dir models/titanet_large

# translation: Meta NLLB-200 distilled 1.3B, converted to CTranslate2 int8 (~1.4 GB; downloads ~5.5 GB first;
# close other apps while it converts)
ct2-transformers-converter --model facebook/nllb-200-distilled-1.3B --output_dir models/nllb_1.3b_ct2_int8 --quantization int8 --low_cpu_mem_usage --copy_files tokenizer.json tokenizer_config.json special_tokens_map.json sentencepiece.bpe.model
```

Optional, the smaller and faster translation model (`--mt-model nllb-600m`; ~620 MB; downloads ~2.5 GB first):

```
ct2-transformers-converter --model facebook/nllb-200-distilled-600M --output_dir models/nllb_600m_ct2_int8 --quantization int8 --low_cpu_mem_usage --copy_files tokenizer.json tokenizer_config.json special_tokens_map.json sentencepiece.bpe.model
```

Notes:
- `hf` and `ct2-transformers-converter` are installed into `.venv` by step 1.
- After converting, the original download in `~/.cache/huggingface/hub/` is no longer needed and can be deleted.
- During the conversion `transformers` may start downloading a second copy of the same weights (`model.safetensors`)
  in the background. The conversion is finished once `models/…/model.bin` and the tokenizer files exist; you can stop
  that extra download with Ctrl+C.

### 3. Route the call audio (BlackHole + Multi-Output Device)

macOS has no input that carries "what the Mac is playing", so the other side of the call cannot be recorded directly.
[BlackHole](https://github.com/ExistentialAudio/BlackHole) is a free virtual audio driver: sound played into it comes
back out as an input that the program can record. A **Multi-Output Device** sends the call to BlackHole **and** to
your headphones, so you still hear it.

```
brew install --cask blackhole-2ch          # restart the Mac if "BlackHole 2ch" does not appear
```

Then open **Audio MIDI Setup** (Spotlight → "Audio MIDI Setup"):

1. **+** (bottom left) → **Create Multi-Output Device**. Rename it **Call Output**.
2. Tick **BlackHole 2ch** and **your headphones**. Do **not** tick the MacBook speakers (see "Why headphones" below).
3. **Primary Device: BlackHole 2ch** (it is always present, so it is the steady clock).
4. **Drift Correction:** tick it on the **headphones only** — every device except the primary one.
5. Sample rate **48.0 kHz** for the group.

In the **call app** (Zoom: Settings → Audio):
- **Speaker: Call Output**
- **Microphone: MacBook Air Microphone** (or a wired mic). Check it before every call: some apps switch to a
  Bluetooth headset's mic on their own.

In **System Settings → Sound → Input**, choose the MacBook microphone too. And allow your terminal app in
**System Settings → Privacy & Security → Microphone** (without it macOS delivers silence; the program detects this
and tells you).

**Why headphones, not the MacBook speakers.** With speakers, the microphone also hears the other side of the call.
In a test with a podcast on the speakers, **10 of 10** call phrases were also printed a second time as `Me`, with
worse audio (TESTS E6). Echo handling is out of scope for the challenge; headphones avoid the problem completely.

**Bluetooth headphones: listening only.** As soon as any app uses a Bluetooth headset's *microphone*, macOS switches
it into headset mode: much lower sound quality both ways, and its output device briefly disappears and comes back,
which can break the "Call Output" group in the middle of a call. Used only as an output, Bluetooth headphones work
(tested with HOCO W35 Max). Charge them first; the Mac's volume keys don't work on a Multi-Output Device, so set the
volume in the call app or on the headphones.

Other systems (not tested here): Windows has WASAPI loopback, Linux the PulseAudio / PipeWire `.monitor` source;
either can replace BlackHole as the `--call` input.

### 4. Check the devices

```
python main.py --list-devices
```
```
 id  name                                     inputs  rate (Hz)
  2  BlackHole 2ch                                 2      48000
  3  MacBook Air Microphone                        1      48000
```

Optional: `python scripts/level_meter.py --list`, then `python scripts/level_meter.py --mic 3 --call 2` shows a live
level bar for both inputs. Speaking should move only the mic bar; the call app's speaker test only the call bar.

---

## Running it

```
python main.py --mic "MacBook Air Microphone" --call BlackHole
```

- `--mic`, `--call`: any unique part of the device name (case does not matter) or its id from `--list-devices`. A name
  that matches nothing, several devices, or an output-only device is refused with a list of candidates.
- `--mt-model nllb-600m`: the smaller translation model — about 2× faster and 0.7 GB lighter, but weaker on casual
  speech (see [results](#measured-results)). Default `nllb-1.3b`.

At start it loads the three models (speech recognition ~10 s, the very first start after an install 70–100 s; speakers
and translation a few seconds each), then prints `Listening.` and an entry for every phrase. **Ctrl+C** stops: the
phrases already heard are still printed, then a summary:

```
Session 160 s; 4 call-side speaker(s) found.
  Me   2 phrases, latency p50 … s, p95 … s, max … s, 0 over 5 s; … non-speech not printed; … audio dropouts
  Call 16 phrases, latency p50 … s, p95 … s, max … s, 0 over 5 s; … non-speech not printed; … audio dropouts
  all  18 phrases, latency p50 2.77 s, p95 … s, max 3.76 s, 0 over 5 s
  latency log: logs/latency.csv
```

A second Ctrl+C stops at once. "Latency" is the time from the end of a phrase to its English line, the number the
brief limits to 5 s. Every printed entry also adds one row of timings (no text) to `logs/latency.csv`.

What you will see:
- The time in brackets is when the phrase **started**, counted from the start of the session.
- Coughs, "hmm" and breaths are not printed (the recogniser writes them as `Հ։`, `Հովհ.`; see D3b).
- A long monologue comes out in pieces of 5–10 s, so you don't wait for the speaker to pause.
- If nothing plays into BlackHole for 10 s, a warning reminds you to set the call app's speaker to "Call Output".

---

## How it works

```
Mic ───────► audio ─► VAD ─────────────────────────┐
                                                    ├─► queue ─► ASR ─► speaker ─► MT ─► terminal
BlackHole ─► audio ─► VAD ─────────────────────────┘           (Armenian) (call side) (English)
```

A **cascade** of small, separate models, cut into **phrases** by voice activity detection. Each step is its own
module in `transcriber/` with a fixed input and output (`transcriber/contracts.py`), built and tested on its own
before being wired together (see [`MODULES.md`](MODULES.md)).

| Step | File | In → out | What it does |
|---|---|---|---|
| audio | `audio.py` | device → 32 ms chunks, 16 kHz mono | One `sounddevice` stream per device. The audio callback only copies each block; a worker thread mixes to mono, resamples to 16 kHz with a streaming resampler (`soxr`, no clicks at block borders) and cuts exact 512-sample chunks. Timestamps are counted from samples, so they don't drift. D7 |
| VAD | `vad.py` | chunks → phrases | Silero VAD scores each chunk. A phrase starts at speech (with 192 ms before it, so the first syllable is kept) and ends after 512 ms of silence. Long speech is cut early: after 5 s at the first short dip, at 10 s at the quietest point. Silence and noise never reach the models. D2 |
| ASR | `asr.py` | audio → Armenian text | NVIDIA FastConformer, RNNT decoder, with punctuation. ~0.3 s per phrase. D1, D1a |
| speakers | `speakers.py` | call-side audio → `Speaker N` | TitaNet turns a phrase into a 192-number "voice fingerprint"; it joins the most similar known speaker if similar enough, else starts a new one (only phrases ≥ 2 s may do that; threshold 0.45, measured). The mic side is `Me` without any analysis. D4 |
| MT | `mt.py` | Armenian → English | NLLB-200 with CTranslate2 (int8). Each phrase is split into sentences, which are translated together and joined, so no sentence is lost. Rules for known weak spots: one-word replies from a small glossary, coughs not printed, no repetition loops. D3–D3c |
| pipeline | `pipeline.py` | — | Wires it all: the main thread feeds both VADs and checks every thread; one worker runs ASR → speaker → MT → print for one phrase at a time. |
| output | `output.py` | — | The entry layout shown at the top. |
| CLI | `main.py` | — | Flags, model loading, Ctrl+C. |

**Why this shape** (D5): the 5 s limit counts from the **end** of a phrase, so waiting for whole phrases costs
nothing, and whole phrases give the recogniser the most context. Streaming recognition (text while someone speaks)
would be much more complex for no gain under this rule. A single speech-to-English model was rejected: none light
enough exists for Armenian, and it could not show the Armenian line.

**Threads:** 2 audio callbacks + 2 audio worker threads (inside `audio.py`), the main thread (VAD, checks, Ctrl+C) and
one model worker. Only the worker prints, so entries never mix. An error in any thread stops the program with that
error — no silent fallbacks.

**Where the 5 s go** (live medians): the VAD needs ~0.3 s of silence to know a phrase ended (often more on the room
mic), ASR ~0.3–0.4 s, speaker ~0.2 s (call side only), translation ~0.7–1.1 s (1.3B; 600M ~0.4–0.5 s), plus
waiting in the queue when both sides talk.

---

## Models: what I chose and why

Armenian is a low-resource language, so every choice was checked against benchmarks **and** then measured on our own
recordings on this Mac. Full reasoning, numbers and rejected options: [`DECISIONS.md`](DECISIONS.md).

### Speech recognition: `nvidia/stt_hy_fastconformer_hybrid_large_pc` (D1, D1a, D1b)

- **Why:** the best open model on the ArmBench-ASR leaderboard on every metric, and clearly best on speech it was not
  trained on — WER on News 23.6 % / Poems 31.3 % / Movies 60.8 % vs 35.2 / 43.9 / 75.0 % for the next open models.
  Only ~115M parameters, decodes in one pass (fast, little risk of inventing text), writes punctuation, CC-BY-4.0.
- **Decoder:** the model has two heads. RNNT made fewer errors than CTC on our recordings (CTC doubled or merged
  letters) for ~10 % more time.
- **Runtime:** NeMo (NVIDIA's own toolkit). The ONNX runtime `onnx-asr` gave letter-for-letter the same text, 1.5–7×
  faster with half the memory; NeMo was kept as the one runtime of the project (no conversion step, one environment).
  Cost: +1.37 GB of memory, 0.3 s per phrase.
- **Alternatives tested on our own audio (D1b):** `seamless-m4t-v2-large` (fluent but rewrites into literary Armenian
  and repeats itself; 3.2 GB), `whisper-large-v3-turbo-armenian` and `whisper-large-hy-2` (misspellings, invented
  punctuation). None was better, and they were 8–10× slower (2.6 s per phrase) or worse (46 s). Not tried: BuzzASR
  (1.55B, too heavy for live use), cloud models (forbidden).
- **Tuning tried and rejected (measured, `eval/run_asr.py`):** beam search (WER 26.7 → 26.2 %, 2.3× slower), longer
  phrases (8 / 15 s instead of 5 / 10 s) and longer pauses before an early cut — none changed more than one or two
  words of 191. The remaining errors are names and casual words, which no setting reaches.

### Voice activity detection: Silero VAD 6.2.3 (D2)

Small (2 MB), MIT, handles noise well; webrtcvad is older and worse on noise. Run directly with onnxruntime (~15 lines)
instead of Silero's own loader, because that loader quietly sets PyTorch to **one thread for the whole program**,
which would slow the recogniser. Same scores as the official wrapper (tested on every recording). Every rule value
(512 ms silence, 5 s early cut, 96 ms dip, 10 s hard cut) was chosen by measuring on 7 recordings and listening to every
cut. Longer phrases (8 s / 15 s) were tried for translation: on a 4-minute podcast they cut fewer sentences in half
(12 of 35 phrases cut mid-speech instead of 21 of 45) and the English read better — but in a live call with 3 people
the speaker labels fell apart (12 call-side phrases became 7 "speakers"), because a long phrase more often holds two
voices. So 5 s / 10 s stays (D2).

### Translation: NLLB-200 distilled 1.3B with CTranslate2 int8, plus a spoken→written word list (D3, D3a–D3d)

- **Why NLLB:** built for low-resource languages; on FLORES-200 Armenian→English the 3.3B NLLB scores above GPT-4
  few-shot (spBLEU 43.0 vs 35.6). The distilled 600M and 1.3B fit the Mac; 3.3B does not.
- **Greedy decoding (beam 1):** with 600M, rated by me on 29 test lines: 21 good / 3 ok / 5 bad; beam 2 was not better and 23 %
  slower. 0.26–0.37 s per line (median), +1.1 GB.
- **1.3B, now the default:** about 2× slower than 600M (median 0.74 s, max 2.0 s per line) and +0.7 GB more memory;
  it changed the English of 70 of 100 test lines, and on casual speech it reads better (e.g. «ջահել ժամանակ» "when
  young": 600M "in the Holocaust", 1.3B "in the past"). Chosen after reading 600M, 1.3B, and each with the word list
  side by side.
- **Spoken→written word list (on):** NLLB learned mostly written Armenian. Before translating, ~110 spoken forms are
  turned into written ones (`ա` → `է`, `էդ` → `այդ`, `ոնց` → `ինչպես`, slang and Russian loans); the Armenian line
  on screen stays as recognised. It changed the input of 33 of 71 real call phrases, fixed errors 1.3B alone did not
  («թե որ թվերին ա ապրել» → "what numbers **he** lived in", not "you"), touched only 5 of 29 clean test lines, all
  correctly, and costs no time.
- **Rules for measured weak spots:** a one-word segment alone gets invented English («Այո։» → "I did."), so 60 common
  replies come from a glossary; the recogniser's text for coughs is not printed; a one-word sentence is translated
  together with its neighbour; `no_repeat_ngram_size=4` stops loops like "Wait, wait, wait…" (which also cost 3 s).
- **Rejected:** local LLMs — the open models on the ArmBench-LLM translation chart that fit 8 GB score lowest and would
  be slower; TranslateGemma (Armenian trained only English→Armenian); NLLB-3.3B (too big).
- **Licence:** NLLB is **CC-BY-NC** (non-commercial) — fine for this challenge, not for a product.

### Speaker identification: NVIDIA TitaNet-Large (D4)

23M parameters, 192-number fingerprint, 0.66 % EER on VoxCeleb1, CC-BY-4.0; trained on English but also on telephone
speech, and voice fingerprints depend little on the language. It runs through the NeMo toolkit the recogniser already
uses, so it adds no library. SpeechBrain ECAPA (0.80 % EER) is the alternative if TitaNet does badly on our calls.
The matching rule was tuned after it failed in a live call (7 "speakers" for 3 people): on real fingerprints of a
2-voice podcast, phrases of 2 s or more match their own speaker at ≥ 0.66 and the other at ≤ 0.35, while shorter
phrases are unreliable (own-speaker similarity down to 0.04). So: **threshold 0.45**, and only phrases **≥ 2 s** may
start or change a speaker (shorter ones take the closest label). That finds the right 2 speakers on the podcast, and
in a 6-minute live call with 3 people on the call side it found 3 (instead of 7 before).

---

## Measured results

All on the MacBook Air M1, 8 GB, 2026-11-01. Sources: [`TESTS.md`](TESTS.md), [`DECISIONS.md`](DECISIONS.md).

**Latency (end of phrase → English line, limit 5 s)**

| Run | Phrases | p50 | max | Over 5 s |
|---|---|---|---|---|
| `main.py`, 600M, headphones, 2 min | 25 | 1.62 s | 2.62 s | 0 |
| **`main.py`, final defaults, Zoom call with 3 people on the call side, 6.3 min** | **81** | **1.93 s** (p95 4.23 s) | **4.64 s** | **0** |
| `main.py`, 1.3B, YouTube podcast + own voice, 2.7 min | 18 | 2.77 s | 3.76 s | 0 |
| `live_asr.py` (no speakers), 10.8 min Zoom call, ASR only | 185 | 1.35 s | 3.76 s | 0 |
| `live_asr.py` with MT (600M), 9 min call | 24 | 2.56 s | 4.16 s | 0 |

**Speech recognition** on 3 spontaneous, spoken-style recordings of mine (121 s, 191 words, references typed by
hand; `eval/real/`): **CER 8.8 %, WER 26.7 %**. About a quarter of the word errors are the reference differing from
what was said (e.g. «է» written where «ա» was said), so the real WER is nearer 20 %. For comparison, ArmBench puts
this model at 23.6 % WER on news and 60.8 % on movie dialogue.

**Memory** (added by each model, measured on its own): ASR +1.37 GB, NLLB-600M +1.07–1.30 GB (1.3B +1.81–1.83 GB),
both VADs ~0.05 GB, TitaNet (not measured alone). The whole program was not measured as one number; estimate ~3.5 GB
with 1.3B (~3 GB with 600M).

**Time per phrase:** ASR 0.27–0.40 s, speaker 0.18–0.25 s (median), translation 0.74 s (1.3B) / 0.37 s (600M) median.

*Note:* only the first row uses the final defaults (NLLB-1.3B + word list, VAD 5 / 10 s, tuned speakers); the others
were earlier set-ups. With 1.3B the slowest phrase came within 0.4 s of the limit (4.64 s); a 10-minute run is still
to do (R7a).

---

## Known limitations

Honest list; most are measured, see TESTS / DECISIONS.

- **Casual Armenian is hard for both models.** Formal speech comes out well. Spoken forms (`ա` for `է`, `էդ`, `ոնց`,
  slang, Russian loans) and names are often wrong in the Armenian, and NLLB — trained mostly on written Armenian —
  often mistranslates casual phrases even when the Armenian is right («ջահել ժամանակ» "when young" became "in the
  Holocaust" with 600M). Garbled Armenian becomes fluent but wrong English: the English line can sound confident
  while being wrong.
- **Call-side speaker labels are tuned on one recording only.** With the first, untuned settings a live call with 3
  people on the call side gave 7 labels. The settings now come from a 2-voice podcast (right 2 speakers, every phrase
  in the right group); a 6-minute call with 3 people on the call side then found 3 speakers, but whether every phrase
  went to the right person was not checked.
  Two people talking back to back with no pause can land in one phrase (one label); overlapping speech is not handled;
  a person who only ever says short phrases (< 2 s) never gets a label of their own.
- **Short phrases:** a one-word phrase gets no new speaker (its fingerprint is weak) and joins the closest one. A real
  one-letter reply said alone (e.g. «Է՞») is hidden together with coughs.
- **Echo:** with laptop speakers the call is transcribed a second time as `Me` (out of scope by the brief) — use
  headphones.
- **The room microphone sometimes hands phrases over late** (p50 up to ~2 s in some calls instead of 0.3 s): the VAD
  waits for silence, and a noisy room or echo keeps it unsure. Every measured phrase still stayed under 5 s; the cause
  is not verified.
- **Very busy calls:** both sides share one model worker. A replay of the busiest logged call stays under 5 s with
  600M; with 1.3B one phrase in 185 would be just over (5.17 s, pessimistic estimate).
  If latency gets tight, `--mt-model nllb-600m` halves the translation time.
- **Memory:** ~3.5 GB of an 8 GB Mac with NLLB-1.3B (~3 GB with 600M). With many other apps open, the Mac may swap and slow down.
- **Long monologues** are cut every 5–10 s; almost half of such cuts fall while the person is still speaking, often
  mid-sentence, and NLLB translates each piece without the one before, so the English of those pieces suffers. Longer
  pieces helped the English but broke the speaker labels (D2).
- **Not tested as a whole:** a 10-minute run of `main.py`, and the whole program with Wi-Fi off (each model was tested
  offline on its own). The first start after an install takes 70–100 s.
- **macOS only as tested**; other systems need their own loopback input.
- **NLLB is non-commercial** (CC-BY-NC).

## What I would improve with more time

1. **Measure speaker labels on real calls** with 3 known voices (the tool is ready: `scripts/try_speakers.py` with a
   turns file); if needed, only *confirm* a new speaker after two similar phrases.
2. **Translation context:** give the translator the previous phrase as context, so a sentence split by a cut is
   translated as a whole; extend the spoken→written word list from more real calls.
3. **Language model fused into the recogniser** (NeMo supports n-gram fusion) built from Armenian text, for names and
   rare words; a bigger, more varied eval set (more voices, call-side recordings).
4. **Room-mic hand-over:** find out why the mic side is sometimes slow (VAD scores in the unsure band) and fix it.
5. **A 10-minute soak test** of the whole program, memory as one number, Wi-Fi-off run.
6. **Lighter runtime:** the ONNX path for the recogniser gave the same text with half the memory (D1a).

---

## Repository layout

```
main.py                    the program (CLI)
transcriber/               the modules: contracts, audio, vad, asr, speakers, mt, output, pipeline
scripts/                   standalone checks per module, the level meter, record.py, live_asr.py (diagnostic run)
tests/                     unit tests: VAD rules, speaker matching, CER/WER metrics
eval/                      evaluation: metrics.py, run_asr.py, reference texts (audio is git-ignored)
briefs/                    one brief per module: contract, checks, status
PLAN.md MODULES.md DECISIONS.md TESTS.md    plan, module split, decision log, test checklist
chats/                     the AI chat history, one file per session
models/  logs/  .venv/     git-ignored: model files, run logs, Python environment
```

## Tools and tests

Run from the repository folder with `.venv` active.

```
python -m unittest tests.test_vad tests.test_speakers tests.test_metrics     # unit tests (no model downloads needed)
python -m scripts.try_audio --selftest           # resampling and chunking, no devices needed
python -m scripts.try_audio --mic microphone --call blackhole --seconds 60   # 60 s live capture check
python -m scripts.record --device blackhole --seconds 10 --out eval/audio/x.wav   # record a test clip
python -m scripts.try_vad eval/audio/x.wav       # how the VAD cuts a recording (writes each phrase as a WAV)
python -m scripts.try_asr eval/audio/x.wav       # Armenian text, time per file
python -m scripts.try_mt eval/mt_sentences.txt   # translation of test lines, time per line
python -m eval.run_asr eval/audio/real --refs eval/real --align   # CER / WER against reference texts
python -m scripts.try_speakers eval/audio/spk_two.wav --turns eval/speakers/spk_two.txt   # speaker accuracy
python -m scripts.live_asr --mic "MacBook Air Microphone" --call BlackHole   # live, with a latency breakdown per phrase
```

`live_asr.py` is the diagnostic version of the program: it prints how long each phrase spent in the VAD, the queue,
ASR and MT, and with `--save` keeps every phrase as WAV + text in `logs/` (only with everyone's consent). It labels the
call side `Call` (no speaker identification).

## How this was built

I worked with Claude (Cowork) as the brief asks, following a plan-first, module-by-module method:

- [`PLAN.md`](PLAN.md): goal, requirements and how each is checked, constraints, milestones, risks.
- [`MODULES.md`](MODULES.md) and [`briefs/`](briefs/): the project split into modules with fixed inputs and outputs,
  each built and tested in its own chat and wired in only after its checks passed.
- [`DECISIONS.md`](DECISIONS.md): every choice with its reasons, numbers and rejected alternatives (D0–D7).
- [`TESTS.md`](TESTS.md): checks written from the brief's requirements, with results, dates and where they ran.
- [`chats/`](chats/): the AI chat sessions, one Markdown file per session. Sessions 02 and 03 are exported from the
  session transcripts; for some sessions the app's export did not work, and the file is a written account or handover
  instead — the original conversations remain available in the app.

Rules kept throughout: fail loudly (no silent fallbacks), measure instead of guessing (several of my own assumptions
were disproved by measurement and recorded as such), verify model names and APIs against their sources, small commits.

## Licences

| Component | Licence |
|---|---|
| NVIDIA FastConformer (hy), NVIDIA TitaNet-Large | CC-BY-4.0 |
| Meta NLLB-200 (600M / 1.3B) | **CC-BY-NC-4.0** (non-commercial) |
| Silero VAD | MIT |
| NeMo toolkit | Apache-2.0 |
| CTranslate2, sounddevice | MIT |
| python-soxr | LGPL-2.1-or-later |
| BlackHole (a separate system driver, not shipped with this repo) | GPL-3.0 |
