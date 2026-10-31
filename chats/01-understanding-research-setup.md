# Session 01 — Understanding the brief, model research, audio setup (M0)

- **Tool:** Claude (Cowork session, model configured as `claude-opus-5-5`)
- **Dates:** 2026-10-23 19:06 → 2026-11-01 01:34 (Asia/Yerevan, UTC+4)
- **Participants:** User (Yenok Martirosyan) and Claude

> **How this file was made.** This is a transcript written out by Claude from the
> conversation itself, at the user's request (no built-in export was used).
> **User messages and Claude's replies are reproduced in full, word for word, in order.**
> Claude's tool calls (file reads, web searches, file writes) are listed in
> *[Tool activity]* blocks as one-line summaries, since their raw outputs are very long.
> Inline diagrams that Claude drew are described in *[Diagram]* blocks.
> Images the user attached are saved in `session-01-assets/`.
> The original conversation remains available in the app.

---

## 1. User — 2026-10-23 19:06

*Attachments: `Mathrix_AI_Coding_Challenge.docx`, `Mathrix_AI_Vibe_Coding_Tips.docx`*

> Here is my task and some tips about how to work with Claude.
>
> I need you to read the Mathrix_AI_Coding_Challenge.docx file line by line, be careful that you don't miss any line or information. Analyze and reason, be sure you understood everything correctly.
>
> Then read Mathrix_AI_Vibe_Coding_Tips.docx file, which is about the ethic and good approach of how to talk to Claude.
>
> Before starting any project or code, let's dive into the cores of the project and understand it deeply. I want to understand the problem that we need to solve here and also main approaches. Explain me the main tools that we need to use for this task in details (e.g. ASR, BlackHole, VAD, etc.).

## 1. Claude

*[Tool activity]*
- Extracted the full text of both `.docx` files with pandoc.
- Listed the internal parts of both Word files; checked comments, footnotes, endnotes and custom properties of the Tips file (all empty).
- Listed the project folder `~/Desktop/armenian-transcriber` (only `.git` and `.DS_Store`).

I read both documents line by line. I also checked the Word files for hidden comments, footnotes or images, and there are none. Your `armenian-transcriber` folder is an empty Git repo, so we're starting fresh. Here's my understanding.

---

## 1. The problem in one paragraph

You're building a **live interpreter for a video call**, running in the terminal. Two audio streams come in: your **microphone**, and the **call audio** coming out of your speakers. The program has to find where each phrase starts and ends, write down the Armenian, translate it to English, and say who spoke. Each line has to appear **no more than 5 seconds after the speaker stops**. Everything runs **on your laptop**: no cloud speech or translation APIs.

Output per segment: **time · speaker · HY text · EN text**.

## 2. Details that are easy to miss

These are the points I think matter most for the design:

1. **The 5 seconds starts when the phrase ends, not when it starts.** The program also has to *decide* that a phrase has ended, which means waiting through some silence first. That waiting counts against the 5 seconds.
2. **The two channels make speaker labels half-solved.** Everything from the mic is "Me", with no voice analysis needed. Only the call side needs to tell voices apart. The interview has **at least two people** on the call side, so this part will be tested live.
3. **"Same person keeps the same label for the whole session."** Labelling each chunk on its own won't work, because labels would reshuffle every chunk. The program needs a memory of voices that lasts the whole session.
4. **Echo is out of scope, but it will still hurt you.** With laptop speakers, your mic hears the call, and the other people get transcribed a second time as "Me". **Use headphones in the interview.** This costs nothing and removes the problem.
5. **"Choose your models deliberately. Armenian is low-resource."** This is the heart of the "Decisions" score. They want you to compare models with numbers and give honest reasons in the README.
6. **The brief and the tips pull in different directions on audio.** Tip 5 says to build a test set of Armenian recordings. The brief says *"Do not commit… audio recordings."* So keep the test audio local and list it in `.gitignore`. Only the reference texts and scripts go into Git.
7. **Chat transcripts are a graded deliverable.** They want every Claude Cowork session, exported in full and unedited, one `.md` per session, in `chats/`. They'll also open the original chats in the interview. **This conversation counts.** Don't use any other AI assistant, and don't delete sessions.
8. **They grade the method as much as the result.** That covers how you broke the problem down, how you tested assumptions, whether you *steer* the AI, and honesty about limits. *"A solution that is honest about its limits beats one that hides them."*
9. **Scope discipline.** No GUI, no installer, no saving transcripts, no speaker names, no other languages. If there's time left, make the core more reliable.
10. **Budget:** about 20 hours over one week (brief dated Oct 21).

## 3. How the Tips doc changes how we work

The tips describe a working style: **you are the architect, I'm the team.** In practice:

- **Plan first.** Write `PLAN.md` before any code, with modules, inputs/outputs, risks and how we'll test.
- **Walking skeleton.** Get the simplest version working end to end first: audio in → text → translation → terminal. Then always fix the weakest part.
- **Separate modules** with clear inputs and outputs, built and tested one at a time, sometimes in separate chats with a short handover note.
- **Measure, don't guess.** Error rate, latency and speaker accuracy, as numbers.
- **`DECISIONS.md`** to log decisions, plus a project rules file.
- **Simple code that fails loudly.** No silent fallbacks. Tip 8 warns that I tend to add these; push back when I do.
- **Check what I claim.** I can invent model names or exaggerate how well a model handles Armenian. Below, I mark what needs checking.
- **Small commits.** If I fail three times on the same thing, step back.

## 4. How the pieces fit together

```
 Mic ───────────► [Capture] ─► [VAD: find phrases] ──► label = "Me" ─────────────┐
                                                                                  ├─► [ASR: Armenian text] ─► [MT: English] ─► Terminal
 Call audio ─► BlackHole ─► [Capture] ─► [VAD] ─► [Speaker embedding + matching] ─┘        (shared worker queue)
 (Zoom/Meet output → Multi-Output Device → your headphones + BlackHole)
```

The usual approach is a **cascade**: separate steps for phrase detection, speech recognition and translation. The alternatives are below. Now each tool in detail.

---

## 5. The core tools

### 5.1 Audio capture: PortAudio / `sounddevice`
- **What it is:** `sounddevice` is the common Python library for audio input. It wraps PortAudio, a cross-platform audio layer. `sd.query_devices()` prints the device list, which meets the requirement that the user picks devices, and `sd.InputStream(device=..., callback=...)` streams audio in.
- **How it works:** the sound card delivers small blocks of samples, for example every 30 ms, to a **callback function**. The callback should do almost nothing: copy the block into a queue and return. Heavy work in the callback causes dropouts.
- **Formats:** devices usually run at 44.1 or 48 kHz, often in stereo. Nearly all speech models want **16 kHz mono float32**, so each stream gets converted to mono and resampled.
- **Two streams:** we open one stream for the mic and one for BlackHole, each with its own queue.

### 5.2 BlackHole + Multi-Output Device (macOS)
- **The problem it solves:** macOS doesn't let apps record what's playing through the speakers. There's no built-in way to capture the other side of a call.
- **BlackHole** is a free, open-source **virtual audio driver** (`brew install blackhole-2ch`). It shows up as both an output and an input device. Whatever is sent to its output comes straight back out of its input with no added delay. It's a virtual cable.
- **The catch:** if Zoom sends audio only to BlackHole, *you* hear nothing. So in **Audio MIDI Setup** you create a **Multi-Output Device** that combines your headphones and BlackHole. The call app (or the system output) goes to that device, so the sound reaches your ears and the program at the same time.
- **Things to watch:**
  - Turn on **Drift Correction** for BlackHole inside the Multi-Output Device, because the two devices' clocks drift apart.
  - macOS volume keys don't work on a Multi-Output Device. Set the volume on the headphones first.
  - Set the call app's **microphone** to your real mic, not BlackHole.
  - Test the setup well before the interview. The brief says so explicitly.
- **Other systems:** Windows has **WASAPI loopback**, and Linux has the PulseAudio/PipeWire **".monitor"** source. You're on a Mac, so BlackHole is the choice.

### 5.3 VAD (Voice Activity Detection)
- **What it is:** a small model that classifies each 10–30 ms of audio as **speech or not speech**. We use it to cut the continuous stream into **phrases**.
- **Why it's essential:**
  1. **Latency:** it decides when a phrase has ended, which starts the 5-second clock.
  2. **Accuracy:** Whisper-type models **invent text when given silence or noise**, such as "Thanks for watching" or subtitle credits, sometimes in Armenian. If we only send speech, most of that goes away.
  3. **Speaker ID:** clean speech-only segments give much better voice fingerprints.
- **Options:**
  - **Silero VAD:** a small neural model, MIT licence, runs on CPU in about a millisecond per chunk, and handles noise well. This is the usual pick.
  - **webrtcvad:** older and rule-based. Very fast, but noticeably worse with noise and music.
- **Settings to tune:** speech threshold, **minimum silence before ending a phrase** (roughly 400–800 ms; shorter is faster but splits sentences), padding before and after, and a **maximum segment length** (roughly 8–15 s). The maximum forces a cut during long monologues, so recognition time stays bounded and latency doesn't run away.

### 5.4 ASR (Automatic Speech Recognition): Armenian speech → Armenian text
This is the **hardest and most important part**, because translation and the live demo depend on it. If the Armenian text is wrong, the English will be wrong too.

- **Two main model families:**
  - **Encoder–decoder (Whisper style):** turns audio into internal features, then *generates* text token by token, like a language model. Output has punctuation and reads naturally. Weaknesses: it can invent text, and it's slower because generation happens one token at a time.
  - **CTC models (wav2vec2 / MMS style):** predict a character for each audio frame in one pass. Fast and less prone to inventing text, but no punctuation or capitals, and spelling is often weaker.
- **Candidates for Armenian.** All of these need checking and measuring; this list is not a verdict:
  - **OpenAI Whisper** (large-v3, large-v3-turbo, medium…). Officially supports Armenian (`hy`), but Armenian had little training data, so expect noticeably higher error rates than for English. How to run it locally on a Mac:
    - **faster-whisper** (CTranslate2): fast on CPU or NVIDIA, but doesn't use the Apple GPU.
    - **mlx-whisper**: runs on the Apple Silicon GPU.
    - **whisper.cpp**: supports Metal (the Apple GPU).
  - **Community Whisper models fine-tuned on Armenian** (on Hugging Face, usually trained on Common Voice / FLEURS). These are often much better than the base model on Armenian, but quality varies a lot, and some exist mostly as demos. **I'll check specific names before we rely on them.**
  - **Meta MMS** (`mms-1b-all` with an Armenian adapter). A CTC model covering over 1,000 languages. Strong baseline, no punctuation.
  - **Meta SeamlessM4T v2.** Does Armenian ASR *and* direct speech-to-English translation in one model. Heavy, and the licence is non-commercial (fine for a challenge, worth noting in the README).
- **Eastern vs Western Armenian:** public datasets are mostly Eastern Armenian, which is what your interviewers in Yerevan will most likely speak. That works in our favour.
- **Metric:** **WER** (word error rate) and **CER** (character error rate). CER is often fairer for Armenian, where words change form a lot. Measure with `jiwer` against your own reference transcripts.
- **Speed matters as much as accuracy:** the best model is useless if it takes 4 s per phrase. We'll measure the **real-time factor** on your machine.

### 5.5 MT (Machine Translation): Armenian text → English
- **Candidates:**
  - **NLLB-200** (Meta; distilled 600M / 1.3B; language code `hye_Armn → eng_Latn`). Built for low-resource languages, and can run fast through CTranslate2. Non-commercial licence.
  - **Opus-MT / Marian** (Helsinki-NLP). Small and very fast; I believe an `hy→en` model exists, *to check*. Quality usually below NLLB.
  - **M2M-100**: an older many-to-many model.
  - **A local LLM** (via Ollama or llama.cpp: Gemma, Qwen, Aya, etc.). Can produce more natural English and use context from earlier lines. But Armenian ability varies a lot between models, it's slower, and it can invent content.
  - **Shortcuts:**
    - Whisper's own `translate` task goes straight from speech to English. But we still need the Armenian text, so we'd run it twice.
    - SeamlessM4T can give both outputs from one model.
- **Points to know:** translating short pieces loses context, and ASR errors carry straight into the translation. Metrics are BLEU / chrF against reference translations. A native speaker (you) checking "is the English understandable?" also counts, and that's the brief's own test.

### 5.6 Speaker identification (diarization) on the call side
- **Diarization** means working out "who spoke when". Here we only need it on the BlackHole stream.
- **How it works:** a **speaker-embedding model** turns a speech segment into a fixed-size vector, a "voice fingerprint". The same voice gives similar vectors whatever language is spoken, so these models work for Armenian.
  - Candidates: **ECAPA-TDNN** (SpeechBrain), **WeSpeaker / pyannote embedding**, **Resemblyzer**.
- **Keeping labels stable over a session (online clustering):**
  - keep one **average fingerprint per known speaker**;
  - for each new segment, compute **cosine similarity** to each one;
  - if the best match is above a threshold, it's that speaker, and we update their average;
  - otherwise it's a **new Speaker N**.
- **Known difficulties:**
  - very short segments ("Այո") give unreliable fingerprints;
  - two people in one segment, or **overlapping speech**;
  - call compression and low audio quality;
  - **the threshold:** too strict creates false new speakers, too loose merges different people.
- **Bigger alternatives:**
  - **pyannote/speaker-diarization-3.1**: excellent, but designed for full recordings, not live streams. Download needs a free Hugging Face token; after that it runs locally.
  - **diart**: streaming diarization built on pyannote.
  - Both are worth knowing about. A simple embedding plus threshold is usually easier to control and explain.

### 5.7 Connecting the pieces: concurrency and latency
- **Model:** a **producer–consumer** design.
  - Capture threads → VAD → a queue of segments with source, timestamps and audio.
  - Worker(s) load each model **once** and run ASR, MT and speaker ID.
  - A printer writes the lines.
- **The danger:** when you and a call participant talk at the same time, both segments wait for the same ASR model. The queue grows and latency goes past 5 s. We need to log **per-segment latency** (phrase end → printed) from day one, so this shows up as a number.
- **Rough budget to check by measuring:** ~0.5 s end-of-phrase silence + ~1–2.5 s ASR + ~0.2–1 s MT + ~0.1 s speaker embedding ≈ **2–4 s**. This leaves little room for slow models.

---

## 6. Main architecture options

| Approach | Description | Pros | Cons |
|---|---|---|---|
| **A. Cascade (VAD → ASR → MT)** | Separate models per step | Modular (matches the "Code" criterion), each part measurable and swappable | Errors carry from one step to the next |
| **B. Joint model (SeamlessM4T)** | One model does ASR + translation | Fewer models | Heavy, harder to tune each part, licence |
| **C. Token-by-token streaming ASR** | Text appears while the person is still speaking | Feels faster | Much more complex; not needed when the deadline is 5 s after the phrase ends |

My current lean is **A, with segments cut by VAD**. That's a hypothesis to test, not a decision yet.

---

## 7. Three things I need from you

Your hardware decides which models are even possible. Before the plan:

1. **Which Mac exactly:** Intel or Apple Silicon (M1/M2/M3/M4…), and **how much RAM**?
2. **What call app** will the interview use (Zoom, Google Meet, Telegram…), and will you use **headphones**?
3. Can you record **5–10 short Armenian clips** (your voice, plus a friend or two over a real call) and type the correct text for each? That becomes our test set, and it stays out of Git.

Once I have these, the next step is a short `PLAN.md` with modules, inputs/outputs, risks and how we test each one, plus an empty `DECISIONS.md`. Then we start the walking skeleton.

---

## 2. User — 2026-10-23 19:28

> Before, I'll give you all those informations (My Mac series, the Armenian clips, etc.) and before starting PLAN.md and DECISIONS.md, I need you to break down the project into meaningful pieces and start to explain me each piece in more details, cause I need to understand what is happening in background of all processes.
>
> So, the first give me the whole image in more details and give me which part comes after what, then when I'll understand, we will pass to the second part.

## 2. Claude

I'll lay out the whole system as one picture first, then walk through each stage in the order the data passes through it.

*[Tool activity] Loaded the inline diagram tool and its diagram guidance.*

The best way to see it is to follow **one spoken phrase** through the system from start to finish. Here's the full map first, then each stage in order, then how the timing works.

*[Diagram: "Pipeline overview". Two lanes side by side. Left lane: Microphone → 1. Capture + convert (16 kHz mono frames) → 2. VAD segmenter (cuts out each phrase) → 3. Label = Me (mic side, no analysis). Right lane: Call audio (BlackHole) → 1. Capture + convert → 2. VAD segmenter → 3. Speaker matching (voice fingerprint to label). Both lanes merge into 4. Segment queue (waits for the worker) → 5. Speech recognition (audio to Armenian text) → 6. Translation (Armenian to English) → 7. Terminal output (time, speaker, HY, EN). Legend: audio side / language models / devices and plumbing.]*

## The big idea in one sentence

The system is a **pipeline**. Audio comes in as an endless stream. The program **cuts it into phrases**, attaches a **who** and a **when** to each one, and then passes each phrase through **two language models** in a row before printing it. The top half runs **twice, once per audio source, in parallel**. The bottom half is **shared**.

---

## Stage 0 — Before anything runs (setup)

This happens once, before the first word is spoken:

- **Audio routing (macOS level, outside Python):** the call app's output goes to a *Multi-Output Device*, which sends it to both your headphones and BlackHole. From the program's point of view, BlackHole becomes an ordinary "microphone" that carries the other people's voices.
- **Device selection:** the program lists audio devices and you pick two, for example `--mic 2 --call 5`.
- **Model loading:** VAD, speaker-embedding, ASR and translation models are loaded **into memory once**. Loading takes seconds to tens of seconds, so it must never happen per phrase.
- **Session clock starts:** this gives the `[00:01:12]` timestamps.

## Stage 1 — Capture + convert

**In:** raw samples from the sound card. **Out:** clean small frames.

- Sound is a list of numbers (**samples**) that measure air pressure. A device at 48 kHz stereo delivers 48,000 numbers per second *per channel*.
- The operating system hands the program a small **block** of samples every few milliseconds, through a **callback** on a high-priority audio thread. The callback's only job is to **copy the block into a queue and return immediately**. If it's slow, the OS drops audio and you get gaps.
- A separate thread then **mixes stereo to mono**, **resamples from 48 kHz to 16 kHz** (what speech models expect), and re-cuts the stream into fixed **frames**, for example 512 samples = 32 ms.

## Stage 2 — VAD segmenter

**In:** a continuous stream of 32 ms frames. **Out:** one **phrase** = a chunk of audio with a start and end time.

- For each frame, the VAD model returns a **speech probability** (0–1).
- A small **state machine** sits on top:
  - *Idle* → probability goes above the threshold → **start recording**, also keeping ~200 ms *before* that point so the first syllable isn't cut.
  - *Recording* → silence lasts longer than X ms (e.g. 500 ms) → **phrase finished** → send it on.
  - *Recording* → phrase gets longer than Y seconds (e.g. 12 s) → **force a cut**, so a long speech doesn't wreck latency.
- **Why this matters so much:** VAD decides *what a phrase is* and *when the clock starts*. Bad cuts break everything downstream: half-words for ASR, two people in one segment for speaker ID, and long waits for latency.

## Stage 3 — Speaker label

**In:** a phrase. **Out:** the same phrase with a `speaker` attached.

- **Mic lane:** the label is simply `"Me"`, with no computation. Which wire the audio came in on tells us who it is.
- **Call lane:**
  1. A speaker-embedding model turns the phrase into a **voice fingerprint**: a vector of ~192–256 numbers that describes *how the voice sounds*, not what was said.
  2. It's compared (cosine similarity) with the stored fingerprint of every known speaker.
  3. **Close enough to one** → that label, and the stored fingerprint is updated slightly. **Close to none** → create `Speaker N+1`.
  4. That stored memory is what keeps labels stable for the whole session.

## Stage 4 — Segment queue

**In:** labelled phrases from both lanes. **Out:** phrases handed one by one to the worker.

At this point a phrase is a small **package of data**:

```
Segment(source="call", speaker="Speaker 1",
        start=72.4s, end=75.1s, audio=<array of 16 kHz samples>)
```

- Both lanes put packages into **one queue**, and a **worker** takes them out in order. The heavy models can only process roughly one thing at a time on a laptop, so the queue lines them up.
- **The hidden risk:** if you and a call participant finish phrases at the same time, one waits behind the other. That waiting **counts toward the 5 seconds**.

## Stage 5 — Speech recognition (ASR)

**In:** the audio array. **Out:** `hy_text = "Բարև, ինչպե՞ս ես։"`

What happens inside (Whisper-type model):

1. The audio is converted to a **log-Mel spectrogram**, a picture of which frequencies are loud over time, close to how the ear hears.
2. An **encoder** (a transformer) reads that picture and builds an internal summary of the sounds.
3. A **decoder** writes text **one token at a time**: "Բա" → "րև" → "," → …, each step looking at the audio summary and the text so far. It's told up front: *language = Armenian, task = transcribe*.

This is usually the **slowest** step and the one with the **most errors** for Armenian.

## Stage 6 — Translation (MT)

**In:** `hy_text`. **Out:** `en_text = "Hi, how are you?"`

- Same encoder–decoder idea, but text to text. The encoder reads Armenian tokens and the decoder writes English tokens.
- **Key fact:** it only sees the *text*, never the audio. Any ASR mistake becomes a translation mistake.

## Stage 7 — Terminal output

**In:** the complete segment. **Out:** the printed lines.

```
[00:01:12] Speaker 1
HY: Բարև, ինչպե՞ս ես։
EN: Hi, how are you?
```

One small detail: only **one thread** should print, otherwise lines from two segments can interleave. It's also the place to **measure latency** (`now − segment.end`) and log it.

---

## What runs at the same time (the "background")

Several things happen **in parallel** all the time:

| Thread | What it does | Must never… |
|---|---|---|
| Mic audio callback | copies blocks into a queue | do anything slow |
| Call audio callback | same, for BlackHole | do anything slow |
| Mic segmenter | convert + VAD → phrases | fall behind real time |
| Call segmenter | convert + VAD + speaker matching → phrases | fall behind real time |
| Worker | ASR → MT for each phrase, in order | be the bottleneck (latency!) |
| Printer / main | prints, logs latency, handles Ctrl+C | interleave lines |

So while the worker is busy translating your last sentence, the audio threads keep recording and the VAD keeps listening for the next phrase. Nothing waits for anything else, except the queue in front of the worker.

## The timing of one phrase

Here's where the 5 seconds go. The numbers are **rough examples to measure later, not facts**:

*[Diagram: "Latency timeline of one phrase". A horizontal timeline. "Person speaking" bar ends at the line "Phrase ends, clock starts". After it: Silence detection (~0.6 s), Speaker matching (~0.1 s), Speech recognition (~1.5 s), Translation (~0.5 s), then "Line printed". A second vertical line marks the "5 s limit". Labels: "About 2.7 s used", "About 2.3 s spare". Numbers illustrative.]*

Three things this picture makes clear:

- The **silence wait** is a trade-off. A shorter wait gives faster output but chops sentences in the middle.
- **Speech recognition is the biggest cost**, and its time depends on the model size *and* your hardware. That's why the Mac question matters.
- The spare time is a **buffer for the queue**. If two phrases arrive together, the second one uses up part of it.

---

## The project broken into pieces (our study order)

| # | Piece | Covers stages | Core question |
|---|---|---|---|
| 1 | **Audio routing + capture** | 0, 1 | How do two live streams reach Python cleanly? |
| 2 | **VAD + segmentation** | 2 | Where does a phrase start and end? |
| 3 | **Speech recognition** | 5 | Which model turns Armenian speech into correct text fast enough? |
| 4 | **Translation** | 6 | Which model turns that text into understandable English? |
| 5 | **Speaker identification** | 3 | How do we tell call participants apart and keep labels stable? |
| 6 | **Pipeline + concurrency** | 4, 7 | How do threads, queues and timing fit together under 5 s? |
| 7 | **Evaluation** | all | How do we *measure* accuracy, latency and labels, not guess? |

This is also roughly the order of the code. Piece 6 starts early in its simplest form, as the "walking skeleton" from the Tips, and grows as the other pieces improve.

If this overall picture is clear, the next step is **Piece 1: audio routing and capture**: what sound is as data, how BlackHole and the Multi-Output Device actually work, and what happens in the callback. You can also click any box in the first diagram to ask about that stage directly.

---

## 3. User — 2026-10-23 20:11

> Explain how call audio reaches the program through BlackHole

## 3. Claude

Here's the route the other people's voices take from the call app to our program, with your mic shown for comparison.

*[Diagram: "Call audio routing through BlackHole". Other people on the call → Call app (Zoom, Meet) "plays their voices" → Multi-Output Device "sends sound to both" → splits into Headphones (real hardware device) → You "hear the call", and BlackHole 2ch "output loops to input" → Our Python program "two input streams". Separately, Microphone "your voice" → Call app, and Microphone → Our Python program. Legend: audio devices / apps / people.]*

## 1. Why we need this at all: how sound normally works on macOS

On a Mac, all sound goes through **Core Audio**, the operating system's audio layer. It manages **devices**, and each device is either:

- an **input** (microphone, line-in), where apps *read* samples, or
- an **output** (speakers, headphones), where apps *write* samples.

When Zoom plays a voice, it writes samples to the chosen output device. Core Audio delivers them to the hardware and they become sound. **That's a dead end for other apps.** macOS offers no built-in "input" that carries what's playing on an output. Our Python program can open microphones, but it has nothing to open that carries the call.

So we need a device that **looks like an output to Zoom and like an input to Python**. That's BlackHole.

## 2. What BlackHole actually is

- **A virtual audio driver.** Technically it's a Core Audio plug-in, installed with `brew install blackhole-2ch`, with no hardware behind it. To macOS it looks like a real sound card called "BlackHole 2ch" that has **both** an output side and an input side.
- **Inside, it's a loop.** Picture a small circular memory buffer:
  - the **output side** writes whatever an app plays into the buffer;
  - the **input side** reads the same samples back out to whoever is recording.
  - Nothing is processed or compressed. The numbers that go in are the numbers that come out, with essentially no added delay.
- **"2ch"** means 2 channels (stereo), which is all we need. The 16ch/64ch versions exist for music production.
- **The name explains itself.** Send sound *only* to BlackHole and it disappears from your ears, into the "black hole". This leads straight to the next problem.

## 3. Why the Multi-Output Device is needed

If Zoom's speaker is set to BlackHole, Python hears the call **but you don't**. You can't hold a conversation like that.

A **Multi-Output Device** is a feature built into macOS, created in the **Audio MIDI Setup** app. It's a "fake" output device that **copies** everything it receives to several real devices at once. We tick two boxes: **your headphones** and **BlackHole 2ch**. Zoom plays into the Multi-Output Device, and the same samples arrive at your ears and at our program.

Two technical settings inside it matter:

- **Clock source (primary device).** Every audio device has its own clock that ticks 48,000 times a second. Two independent clocks are never exactly equal; one might run at 48,000.3 Hz and the other at 47,999.8 Hz. The Multi-Output Device follows one of them, the **primary device**. That should be the **headphones**, the real hardware.
- **Drift correction.** Enable it on BlackHole. It adds or removes an occasional sample so BlackHole stays in step with the primary clock. Without it, small clicks or glitches can appear over a long session.

## 4. The journey of one sentence, step by step

Say Speaker 1 says "Բարև, ինչպե՞ս ես":

1. **Their computer** records it, compresses it (the Opus codec, typically), and sends packets over the internet.
2. **Your call app** receives the packets, decodes them back into samples, and writes them to its *speaker device*, which is the Multi-Output Device.
3. **Core Audio** sends a copy to your headphones (you hear it) and a copy into BlackHole's output side.
4. **BlackHole** passes the samples through its loop to its input side.
5. **Our program** has BlackHole open as an input stream, for example with `sounddevice`. Every few milliseconds Core Audio calls our **callback** with the next block of samples, exactly as it would for a real microphone.

From that point on, Python **can't tell** that BlackHole isn't a microphone. It's just "input device #5, 2 channels, 48 kHz". This is also why the *same code* handles both lanes; only the device number differs.

## 5. Why this lane is so clean, and what that means for us

- **It's a digital copy, not sound through the air.** There's no room echo and no keyboard noise, at the same quality the call app decoded. That's good for ASR and speaker matching.
- **Your own voice is normally not in it.** Call apps don't play your voice back to you. So the BlackHole lane holds **only the other people**, which is why "mic = Me, BlackHole = others" works without extra logic.
- **One exception.** If a participant has an echo problem (speakers plus mic, no echo cancellation), your voice can come back through *their* microphone. Our program would then label it as a call speaker. Echo is out of scope, but it's worth one line in the README's limitations.
- **The audio is already compressed by the call codec,** which makes voices a little less distinct. That matters later for speaker identification.

## 6. A design choice: route only the call app, or the whole Mac?

- **Option A (my recommendation):** set **only the call app's speaker** to the Multi-Output Device, and keep the system output on your headphones. Then notification sounds and YouTube **don't end up in the transcript**.
- **Option B:** set the **whole system output** to the Multi-Output Device. Simpler, but every sound the Mac makes gets captured.

Zoom, Google Meet (in Chrome) and Telegram all have a speaker setting. We'll confirm the exact menu for whichever app the interview uses.

## 7. Pitfalls that commonly break this setup

| Problem | What you notice | Cause / fix |
|---|---|---|
| Python records only zeros | Level meter is flat | macOS **Microphone permission** missing for Terminal/iTerm/VS Code (System Settings → Privacy & Security → Microphone). macOS asks for it even for BlackHole. |
| BlackHole missing from the device list | Not shown after install | Core Audio didn't reload the driver; restart the Mac (or the audio service). |
| You hear nothing | Call is silent | Call app's speaker set to BlackHole alone instead of the Multi-Output Device. |
| Others hear nothing / hear themselves | Complaints on the call | Call app's **microphone** set to BlackHole by mistake. It must be the real mic. |
| Volume keys don't work | Volume stuck | Normal: macOS can't control a Multi-Output Device's volume. Set it on the headphones in Audio MIDI Setup or in the call app. |
| Clicks or garbled audio over time | Artefacts after minutes | Drift correction off, or **sample rates differ**. Set the headphones and BlackHole to the same rate (48 kHz) in Audio MIDI Setup. |
| AirPods sound bad | Low quality | If AirPods' **own mic** is in use, macOS switches them to a low-quality headset mode. Use wired headphones, or the Mac's mic with AirPods only for listening. |

## 8. An alternative worth knowing (for the README's "alternatives considered")

Newer macOS versions can capture app or system audio **without** a virtual driver, through ScreenCaptureKit and Core Audio "process taps". It's cleaner for end users, but it's hard to reach from Python and needs more native code. BlackHole is the standard, well-documented choice and is what the brief suggests. I'd mention the alternative in the README and **check the details** before writing about it.

---

**How we'll test this piece in practice:** we'll write a tiny script that lists devices and shows a **live level meter for both inputs**. Play a YouTube video through the Multi-Output Device: the BlackHole meter should move and the mic meter shouldn't. Speak, and the reverse should happen. That's our first small step of the walking skeleton.

Next in Piece 1 is **what the program does with those samples**: what audio looks like as numbers, the callback, and converting 48 kHz stereo to 16 kHz mono. Or you can go deeper into any box in the diagram first.

---

## 4. User — 2026-10-23 20:28

> Ok, good, I got this. Now before starting our project, we need to understand which models should we use for this case and here we need to be very careful, cause it's very important how good our output will be. Let's analyze and understand which models are the best for this case. We need to run everything locally, no API. My Macbook air has 8gb ram (this will be helpful to choose the best model).
>
> Be careful, because we need to have a good output and also everything should stay below 5 seconds and everything should be authentic. Suggest the best models for each problem and I'll check them

## 4. Claude

I'll research current options for each stage, focusing on Armenian quality, what fits in 8 GB, and speed on a fanless MacBook Air. I'll check every model name and claim against its source before recommending it.

*[Tool activity]*
- Created a task list: research Armenian ASR models; research Armenian→English MT models; research VAD and speaker embedding models; check memory/latency budget and write the recommendation.
- Web searches: Armenian Whisper fine-tunes and WER on Common Voice/FLEURS; Meta Omnilingual ASR for Armenian; Whisper Armenian fine-tunes on Hugging Face.
- Read model cards: `BuzzASR/armenian` (Whisper-large-v3 fine-tune; FLEURS CER 3.72 / WER 11.89; Common Voice 25 CER 0.65 / WER 2.41; Whisper-large-v3 zero-shot CER 13.79 on FLEURS); `Chillarmo/whisper-large-v3-turbo-armenian` (0.8B; WER 15.31 / CER 2.86 on its own Common Voice 20 split; Apache-2.0); `alphaedge-ai/whisper-small-hye-32768` (vocabulary-trimmed Whisper small, no WER reported). Read the Springer paper "Automatic speech recognition for Armenian dialects" (Whisper large-v3 fine-tuned: average WER 15.75%, CER 5.33% across dialects).
- Read the BuzzASR organisation page and paper (arXiv 2609.09554): no Armenian numbers for other systems in the retrieved text; no discussion of Common Voice train/test sentence overlap.
- Checked Qwen3-ASR language list: Armenian not supported. Searched Omnilingual ASR specs: on-device sizes 300M–7B; no Armenian-specific numbers found.
- Found the Hugging Face Open ASR Leaderboard pull request adding Armenian (no results yet), which named `nvidia/stt_hy_fastconformer_hybrid_large_pc`. Read its model card (PR branch): ~115M params; 296.19 h of Armenian training data; Transducer WER 9.90 (MCV 17) / 12.32 (FLEURS), CTC 11.19 / 13.23; punctuation and capitalization; CC-BY-4.0; non-streaming. Read the ONNX version card (OpenVoiceOS, runs with `onnx-asr`, CTC head).
- MT: FLORES-200 hye→en leaderboard (NLLB 3.3B spBLEU 43 / COMET-22 88.3; GPT-4 few-shot 35.6 / 86.2); low-resource MT benchmark paper (no Armenian; NLLB best on FLORES for most languages); TranslateGemma news and technical report (Armenian only in en→hy training, not evaluated); NLLB-200 distilled 600M card (CC-BY-NC, research use). Could not confirm that an Opus-MT hy→en model exists.
- VAD / speakers: Silero VAD v6.2 card (≈2 MB, 512-sample chunks at 16 kHz, MIT weights); multilingual zero-shot speaker verification paper (TitaNet vs ECAPA roughly equal across 5 languages); SpeechBrain ECAPA (0.80% EER VoxCeleb1-test, Apache-2.0).
- Marked all four tasks completed.

I've checked the current options against their model cards and papers. Below is my recommendation for each stage, with the evidence behind it. A **✔︎** means I confirmed the claim in a primary source; **⚠︎** means it's my estimate or I couldn't confirm it, so treat it as something to measure.

## First: what 8 GB really means

A MacBook Air's 8 GB is **shared** between macOS, the call app and the GPU. macOS plus Zoom or Chrome-with-Meet take roughly 4 GB, so our program should stay **under about 3–3.5 GB** for all models together. If it goes over, the Mac starts swapping to disk and latency jumps unpredictably. The Air also has **no fan**, so it slows itself down under long heavy load. Both facts favour **small, efficient models**, and that's what the shortlist does.

---

## 1. Speech recognition (ASR): the most important choice

| Candidate | Size | Reported Armenian accuracy | Notes |
|---|---|---|---|
| **NVIDIA FastConformer-Hybrid Large (hy)** ✔︎ | **~115M** | WER **9.90%** Common Voice, **12.32%** FLEURS (Transducer); 11.19 / 13.23 (CTC) | Armenian-only, trained on **296 h** of Armenian. Outputs **punctuation**. CC-BY-4.0 licence. Not streaming (fine for us). |
| **BuzzASR/armenian** ✔︎ | 1.55B (Whisper large-v3) | CER **3.72%** / WER **11.89%** FLEURS; CER 0.65% on Common Voice | New (EMNLP 2026). Claims the lowest CER of all open systems, but heavy for 8 GB, and the replaced tokenizer may not work with Mac Whisper runtimes ⚠︎ |
| **Chillarmo/whisper-large-v3-turbo-armenian** ✔︎ | 0.8B | WER 15.31%, CER 2.86% (on its own Common Voice split) | Apache-2.0. Works with the standard Whisper tools (mlx-whisper). Weaker evidence. |
| OpenAI Whisper large-v3, no fine-tune ✔︎ | 1.55B | CER **13.79%** FLEURS (as reported by BuzzASR) | Useful only as a **baseline**: much worse than the fine-tunes. |

**Recommendation: NVIDIA FastConformer as the main model, Chillarmo's Whisper-turbo as the challenger, and BuzzASR as an offline quality ceiling.** Why:

- **Its accuracy is in the same range as the best, at about a tenth of the size.** 12.32% WER on FLEURS vs 11.89% for BuzzASR, with 115M vs 1.55B parameters.
- **Speed:** it doesn't generate text token by token like Whisper, so on a laptop CPU it should take a fraction of a second per phrase ⚠︎ (to measure). That leaves most of the 5 seconds free.
- **Less "invention":** Whisper-type models are known to hallucinate whole sentences from noise. CTC/Transducer models make spelling errors instead, which is a more honest kind of failure.
- **Two ways to run it:**
  1. **NeMo** (full Transducer decoder, best accuracy, heavy install on Mac ⚠︎);
  2. **ONNX via `onnx-asr`** (light install, CTC decoder, about 1 point worse WER) ✔︎.

**Important caveat:** these numbers come from **different test sets with different text normalisation**, so they aren't fully comparable. Common Voice also reuses sentences between training and test data, which inflates scores; BuzzASR's 0.65% looks like that to me ⚠︎. This is exactly why the Tips say to build **our own test set**. Your clips will decide, not the model cards.

**Excluded, with reasons:**
- **Qwen3-ASR**: Armenian isn't among its 30 languages ✔︎.
- **Omnilingual ASR**: covers Armenian, but I found no Armenian-specific numbers, and BuzzASR reports beating it. The 7B version is too big.
- **SeamlessM4T v2**: about 2.3B, non-commercial licence, too heavy.
- **Whisper-small fine-tunes**: ~24% WER, too weak.
- **MMS**: no punctuation, older.

## 2. Translation (Armenian → English)

| Candidate | Evidence | Notes |
|---|---|---|
| **NLLB-200 distilled 1.3B** ✔︎ | The 3.3B NLLB scored spBLEU **43.0** / COMET **88.3** on FLORES hye→en, **above GPT-4** (35.6 / 86.2) | Built for low-resource languages. Runs fast with CTranslate2 int8 (~1.3 GB ⚠︎). |
| NLLB-200 distilled 600M ✔︎ | Same family, smaller | Fallback if 1.3B is too slow or too heavy. |
| TranslateGemma 4B ✔︎ | Armenian is in training **only English→Armenian**, with **no Armenian evaluation** in the report | Not the right direction. LLMs are also slower and heavier. |

**Recommendation: NLLB-200 distilled 1.3B**, with 600M as the fallback. The licence is **CC-BY-NC** (research use only) ✔︎. That's fine for a challenge, but it goes in the README. One gap: I couldn't find Armenian-specific scores for the *distilled* versions, only for the 3.3B, so we'll compare 600M and 1.3B on your sentences. I also couldn't confirm that an Opus-MT Armenian→English model exists, so I've left it out.

## 3. VAD

**Silero VAD v6** ✔︎. MIT licence, about 2 MB, processes 512-sample (32 ms) chunks at 16 kHz in a few milliseconds. It's effectively the standard choice; webrtcvad is older and handles noise worse.

## 4. Speaker embeddings

**SpeechBrain ECAPA-TDNN (`spkrec-ecapa-voxceleb`)** ✔︎. Apache-2.0 licence, **0.80% EER** on VoxCeleb1. EER is the error rate when deciding whether two clips are the same voice, so lower is better.

Speaker fingerprints don't depend much on language. A study testing models on five languages without retraining found ECAPA and NVIDIA's TitaNet roughly equal, each better on some languages ✔︎. If we install NeMo for ASR anyway, **TitaNet** comes free and is a natural alternative. WeSpeaker ResNet34 via pyannote is a third.

---

## Rough fit: memory and latency (to check by measuring)

| Stage | Model | Memory ⚠︎ | Time per phrase ⚠︎ |
|---|---|---|---|
| VAD | Silero v6 | ~0.01 GB | ~ms per frame |
| Speaker | ECAPA | ~0.1 GB | ~0.05 s |
| ASR | NVIDIA FastConformer | ~0.5–1 GB | ~0.1–0.4 s |
| MT | NLLB 1.3B int8 | ~1.3–1.5 GB | ~0.3–1 s |
| **Total** | | **~2–2.7 GB** | **~1–2 s + ~0.5 s silence wait** |

That fits in 8 GB and leaves a comfortable buffer under 5 s. With BuzzASR instead, ASR alone would be ~3 GB+ and much slower, which is why it's only the offline comparison.

## What to check before we decide

1. **Read the model cards** (links below). Note: I could only open the NVIDIA card on a pull-request branch, so check its main page too.
2. **Tell me your chip** (M1, M2, M3…), since it changes speed a lot.
3. **Record the test clips.** Then a small benchmark script runs **NVIDIA (ONNX and NeMo) vs Chillarmo-turbo vs BuzzASR** for WER, CER and time, and **NLLB 600M vs 1.3B** for speed plus your judgement of the English. The numbers go into `DECISIONS.md`.

Sources:
- [NVIDIA FastConformer-Hybrid Large (hy) model card](https://huggingface.co/nvidia/stt_hy_fastconformer_hybrid_large_pc/blob/refs%2Fpr%2F3/README.md) · [ONNX version](https://huggingface.co/OpenVoiceOS/stt_hy_fastconformer_hybrid_large_pc_onnx) · [Open ASR Leaderboard Armenian PR](https://github.com/huggingface/open_asr_leaderboard/pull/215)
- [BuzzASR/armenian](https://huggingface.co/BuzzASR/armenian) · [BuzzASR paper](https://arxiv.org/pdf/2609.09554)
- [Chillarmo/whisper-large-v3-turbo-armenian](https://huggingface.co/Chillarmo/whisper-large-v3-turbo-armenian)
- [Qwen3-ASR language list](https://huggingface.co/bezzam/Qwen3-ASR-1.7B-hf) · [Omnilingual on Apple Silicon](https://soniqo.audio/guides/omnilingual) · [ASR for Armenian dialects (Springer)](https://link.springer.com/article/10.1007/s10772-026-10255-y)
- [FLORES-200 hye→en leaderboard](https://www.sota2.com/research/sota/machine-translation-on-flores-200-hye-en-test) · [NLLB-200 distilled 600M card](https://huggingface.co/facebook/nllb-200-distilled-600M/blob/main/README.md) · [TranslateGemma technical report](https://arxiv.org/pdf/2601.09012)
- [Silero VAD v6 card](https://huggingface.co/openEuler/silero-vad) · [ECAPA (spkrec-ecapa-voxceleb)](https://www.promptlayer.com/models/spkrec-ecapa-voxceleb) · [Multilingual speaker verification study](https://arxiv.org/pdf/2404.01981)

---

## 5. User — 2026-10-23 21:19

*Attachment: screenshot of the ArmBench-ASR leaderboard, open models, WER — see [`session-01-assets/armbench-asr-leaderboard.png`](session-01-assets/armbench-asr-leaderboard.png)*

> Here is the TOP ASR models for Armenian. Yeah, the NVIDIA's FastConformer is the first open source model, but why we should use exactly that one?

## 5. Claude

I'll quickly look up where this leaderboard comes from, since how it was built affects how much weight its numbers deserve.

*[Tool activity]*
- Web search for the leaderboard; found ArmBench-ASR by Metric AI Lab.
- Read the leaderboard page: 34 systems; ranks #1–10 are cloud services (best: google/gemini-2.5-pro 13.80 combined WER; wavam/default 19.13; google/gemini-3.6-flash 19.42); NVIDIA #11 with 19.86 combined; dataset descriptions and decoder used not given; BuzzASR not listed.

## Short answer

Two reasons together. On the parts of this leaderboard that are the **fairest test** (speech no model was trained on), NVIDIA's model is **clearly the best open model, by a wide margin**. And it's the **only** strong model in this list that fits an 8 GB MacBook Air under the 5-second limit. The next-best models are either much heavier or noticeably worse.

The leaderboard is [ArmBench-ASR by Metric AI Lab](https://metric-ai-armbench-asr.static.hf.space/index.html). It ranks 34 systems, and ranks #1–10 are all **cloud services** (Gemini, ElevenLabs, HiSpeech, Wav.am…). The brief forbids those, so for us NVIDIA is effectively #1.

## 1. How to read the table: not every column is equally fair

- **Common Voice and FLEURS are "home ground".** NVIDIA trained on both (its card lists Common Voice 17 and FLEURS training data), and so did most Armenian fine-tunes. Common Voice also reuses sentences between its training and test parts. High scores there partly measure *memory*, not *understanding*.
- **Poems, Movies and News are "away games".** They're new data the models most likely never saw. This is the best predictor of how a model will cope with **your interview call**.

On the away games:

| Dataset | NVIDIA | Best other open model | NVIDIA makes… |
|---|---|---|---|
| **News** | **23.55** | 35.18 (omniASR-LLM-3B) | ~33% fewer errors |
| **Poems** | **31.28** | 43.93 (Seamless v2) | ~29% fewer errors |
| **Movies** | **60.78** | 75.04 (cast/whisper-mwa-hy) | ~19% fewer errors |

It wins **all three** by a large margin. On FLEURS it's essentially tied with Seamless (15.00 vs 14.44). Its combined score (19.86) is also **almost level with paid cloud systems** such as Wav.am (19.13) and Gemini 3.6 Flash (19.42).

## 2. This table corrects something I told you earlier

Look at **chillarmo/whisper-large-v3-turbo-armenian**: 12.94 on Common Voice, but **24.69 on FLEURS** and **82.01 on Movies**. That's a model **over-tuned to Common Voice**: good on its home dataset, weak elsewhere. Its model card's 15.31% WER was measured on its *own* Common Voice split, so it looked better than it is. I listed it as our "challenger". **That was wrong, and I'm withdrawing it.** It's a good example of Tip 9: a model card's number is a claim, not a fact.

## 3. Constraint check: the top 4 open models

| | NVIDIA FastConformer | Seamless M4T v2 large | Chillarmo turbo | arampacha whisper-large-hy-2 |
|---|---|---|---|---|
| Size | **~115M** | ~2.3B | ~0.8B | ~1.55B |
| Fits 8 GB alongside translation + call app | **Yes, easily** | No (~5 GB in fp16) | Yes | Tight |
| Speed | **One pass, no token-by-token loop** | Slow, generates tokens | Medium | Slow |
| Hallucination risk | **Low** (CTC/Transducer) | Medium | High (Whisper) | High (Whisper) |
| Punctuation | Yes | Yes | Yes | Yes |
| Licence | **CC-BY-4.0** | CC-BY-NC | Apache-2.0 | (to check) |
| Away-game accuracy | **Best** | 2nd | Weak | 3rd |

No other model wins on even one row that matters to us. That's the real "why": **best accuracy and best fit at the same time**, so we don't have to trade one for the other.

## 4. What I'm *not* claiming

- **Movies at 60.78% WER is bad in absolute terms.** Movies is the closest category to real conversation (casual speech, overlap, emotion), and a video call is conversation. Even the best open model gets roughly every second word wrong there. We should expect **visible errors in the live demo** and say so in the README.
- **We don't know NVIDIA's full training data.** 214 h are "proprietary", plus audiobooks (Grqaser). Overlap with the Poems or News sets is unlikely, since the News data came from Infocom through the benchmark team, but we can't rule it out ⚠︎.
- **The table shows raw WER.** That counts punctuation and spelling differences as errors. Click the **CER** and **WER-norm** tabs and check that NVIDIA stays on top there too. That's a 30-second check for you.
- **The leaderboard doesn't say which decoder was used** (Transducer or CTC). We'll test both ourselves.
- **BuzzASR isn't on the leaderboard** (it's newer). Its own FLEURS score of 11.89 can't be compared directly with the 15.00 here, because normalisation differs. It's worth **one offline test** as a quality ceiling, nothing more.

## 5. What would change the decision

Only **our own measurements**: if, on recordings of real Armenian calls, another model that fits 8 GB and 5 s gets clearly fewer errors. So the revised ASR plan is:

1. **Main model: NVIDIA FastConformer.** Compare the **Transducer decoder (NeMo)** with the **CTC decoder (ONNX)** for accuracy and speed.
2. **BuzzASR**: run offline on the same clips, only as a ceiling for the README.
3. Seamless and the Whisper fine-tunes: excluded, with the leaderboard numbers above as the reason in `DECISIONS.md`.

One open question from before: **which chip is in your MacBook Air (M1/M2/M3/M4)?** It decides whether NeMo is fast enough or whether we go with the ONNX route.

Sources:
- [ArmBench-ASR leaderboard (Metric AI Lab)](https://metric-ai-armbench-asr.static.hf.space/index.html)
- [NVIDIA FastConformer-Hybrid Large (hy) model card](https://huggingface.co/nvidia/stt_hy_fastconformer_hybrid_large_pc/blob/refs%2Fpr%2F3/README.md)
- [Chillarmo/whisper-large-v3-turbo-armenian](https://huggingface.co/Chillarmo/whisper-large-v3-turbo-armenian)
- [BuzzASR/armenian](https://huggingface.co/BuzzASR/armenian)

---

## 6. User — 2026-10-23 21:24

> Yeah, I also checked for all Metrics, NVIDIA's model is the first one and it fits our storage requirements. We will go with that

## 6. Claude

Decision made: **ASR = NVIDIA FastConformer-Hybrid Large (hy)**. You checked the other metrics yourself rather than taking my word for it, which is exactly the habit the evaluators will look for in the chats.

Here's the entry I'd put in `DECISIONS.md` when we create it:

```markdown
## D1 — ASR model: nvidia/stt_hy_fastconformer_hybrid_large_pc (2026-10-23)
**Why:** Best open model on ArmBench-ASR across all metrics (WER, CER, normalised),
and clearly best on unseen domains (News 23.55, Poems 31.28, Movies 60.78 WER vs
35.18 / 43.93 / 75.04 for the next open model). ~115M params → fits 8 GB with room
for translation; single-pass decoding → low latency, low hallucination risk.
Punctuation output. CC-BY-4.0.
**Rejected:** Seamless M4T v2 (2.3B, too heavy, NC licence); Whisper fine-tunes
(chillarmo turbo over-fitted to Common Voice: 12.94 CV vs 82.01 Movies);
omniASR / MMS (much higher WER); cloud models (forbidden by brief).
**Known risk:** conversational speech is hard (Movies 60.78 WER) → expect errors live.
**Still open:** Transducer decoder (NeMo) vs CTC decoder (ONNX). Decide by measuring
accuracy + speed on our own clips.
```

Decisions still open, each to be settled by measuring:

1. **ASR decoder:** Transducer via NeMo or CTC via ONNX. This depends on your chip and on install effort.
2. **Translation:** NLLB-200 distilled **600M vs 1.3B**, a trade between speed and quality on your sentences.
3. **Speaker embeddings:** **ECAPA** (SpeechBrain) or **TitaNet**, which comes free with NeMo if we choose the Transducer route.

To move forward I need the two things from earlier: your **MacBook Air chip** (M1/M2/M3/M4) and, when you're ready, the **test clips**. They should include at least one recorded over a real call, since that's the hardest and most realistic case. Once I have the chip, I'll draft `PLAN.md` with `DECISIONS.md` (starting with D1 above) in your repo.

---

## 7. User — 2026-10-23 23:45

> Ok, so let's use your suggested models. I checked them too and they seem good fits for this. Let's start the project as I said. Ask questions for being more clear.

## 7. Claude

I'll start with a quick check of what I can see from here, so I only ask you what I can't find out myself.

*[Tool activity] Ran a shell on the linked computer: architecture `aarch64` (Apple Silicon). The project folder could not be mounted in that shell (reachable only through file listing / copy tools).*

Your Mac is Apple Silicon (I confirmed that from here). Four quick questions decide the plan's details:

*[Questions asked in the app, with the user's answers]*
- *Which chip is in your MacBook Air?* → **M1**
- *Which call app will the interview most likely use?* → **Don't know yet**
- *What headphones will you use during the interview?* → **Wired headphones**
- *How do you want us to work on code?* → **Step by step, I review (Recommended)**

M1 with 8 GB is the tightest of the options, so the plan keeps memory and speed checks front and centre. I'll now write `PLAN.md` and `DECISIONS.md` into your repo for you to review.

*[Tool activity] Wrote `PLAN.md` and `DECISIONS.md` and copied both into `~/Desktop/armenian-transcriber/`.*

I've added `PLAN.md` and `DECISIONS.md` to your `armenian-transcriber` folder.

- **`PLAN.md`** covers the goal, a table of requirements and how we'll check each one, your M1 / 8 GB limits, the architecture, and what each module takes in and puts out. It then sets out seven milestones with time estimates (about 20 h), the risks, how we'll test, and the project rules.
- **`DECISIONS.md`** records each choice with its numbers and status. The NVIDIA ASR model is **Decided**. Silero VAD, NLLB translation and the overall design are **Tentative** until we measure them. The speaker model is still **Open**.

I can write files into your folder, but I can't run commands there, including `git`. So the code runs in your Mac's Terminal, and you do the commits. That also fits the step-by-step review you chose.

Please read both files and tell me anything you'd change. Then make the first commit:

```bash
cd ~/Desktop/armenian-transcriber
git add PLAN.md DECISIONS.md
git commit -m "Add project plan and decision log"
```

Before milestone M0 (environment and audio setup), I need three things from you. You can find them by running these in Terminal:

1. **Is Homebrew installed?** Run `brew --version`.
2. **Which Python do you have?** Run `python3 --version` and `which uv`. The plan suggests `uv` with Python 3.11, but you can choose something else.
3. **Is there a GitHub repo for this yet?** If so, send the link; if not, we'll create one.

---

## 8. User — 2026-10-23 23:52

> My brew version is "Homebrew 7.0.10", python version is "Python 3.12.3" and I don't have uv package.
>
> This folder, that you are working on is a repository itself, here is the links
> https://github.com/yeknock/armenian-transcriber.git

## 8. Claude

Python 3.12.3 is fine for every library we picked, so we don't need `uv`. We'll use Python's built-in `venv` with a `requirements.txt`, which is one less tool to install. Now I'll write the files for **milestone M0**: environment setup, audio routing, and a level-meter script that proves both inputs reach Python.

*[Tool activity]*
- Wrote `.gitignore`, `requirements.txt` (`numpy`, `sounddevice`) and `scripts/level_meter.py`; added entry D0a (Python environment + repo link) to `DECISIONS.md`.
- Syntax-checked `scripts/level_meter.py` (`py_compile`: OK).
- Copied all four files into the repo on the user's Mac.

I've added the files for milestone M0 to your repo:

- **`.gitignore`** keeps model weights, audio files, `.venv` and secrets out of Git, as the brief requires.
- **`requirements.txt`** lists only `numpy` and `sounddevice` for now.
- **`scripts/level_meter.py`** is a test tool, not the real capture code. It opens two input devices and shows a live loudness bar for each. If a device delivers nothing but exact silence, it prints a clear warning naming the two likely causes. It also counts dropouts, which are moments when audio was lost.
- **`DECISIONS.md`** has a new entry, D0a, recording the Python environment choice and the repo link.

I only checked that the script's syntax is valid. Its first real run will be on your Mac.

## M0 steps, in order

**1. Commit and push.**
```bash
cd ~/Desktop/armenian-transcriber
git remote -v          # should show github.com/yeknock/armenian-transcriber
git add .
git commit -m "M0: gitignore, requirements, level meter script"
git push
```

**2. Install BlackHole.** It will ask for your password.
```bash
brew install --cask blackhole-2ch
```
If "BlackHole 2ch" doesn't show up in the next step, restart the Mac.

**3. Create the Multi-Output Device.** Plug in your wired headphones first. Then open **Audio MIDI Setup** (Spotlight → "Audio MIDI Setup").
- Click **+** at bottom-left, then **Create Multi-Output Device**.
- Tick **External Headphones** and **BlackHole 2ch**.
- Set **Primary Device** to External Headphones, and tick **Drift Correction** next to BlackHole.
- Double-click its name and rename it to **Call Output**.
- Click External Headphones and BlackHole 2ch in the left list and check that both use **48,000 Hz**.

**4. Route test audio.** For this test only, go to System Settings → Sound → Output and choose **Call Output**.

**5. Set up Python.**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**6. Run the meter.**
```bash
python scripts/level_meter.py --list
python scripts/level_meter.py --mic <MacBook Air Microphone id> --call <BlackHole 2ch id>
```
The first time you run it, macOS will ask whether Terminal may use the microphone. Click **Allow**.

**7. Run three checks**, each for about 5 seconds:

| Action | MIC bar | CALL bar | You hear |
|---|---|---|---|
| Stay silent | low | empty | — |
| Speak | **moves** | stays empty | — |
| Play a YouTube video | (almost) still | **moves** | the video in your headphones |

Send me the `--list` output and the result of each check, including the dropouts number. If something doesn't match the table, paste exactly what you saw and we'll fix that before moving on.

---

## 9. User — 2026-10-24 00:21

> First of all. I want you to explain what are you doing and explain each step in more details.
>
> I got some problems with parsing, there is an parse error near `\n', explain what is the problem and only then fix it.

## 9. Claude

## What caused the error

`parse error near '\n'` comes from **zsh, your Terminal's shell**, not from Python. It means zsh couldn't even understand the command line, so Python never started.

The cause is almost certainly my instruction. I wrote:

```
python scripts/level_meter.py --mic <MacBook Air Microphone id> --call <BlackHole 2ch id>
```

I meant the angle-bracket parts as **placeholders**, "put the number here". But in zsh, `<` and `>` are special characters:

- `<` means "read input from this file".
- `>` means "write output to this file".

So zsh read the end of the line, `... id>`, as "write output into the file named…", and then found only the end of the line (`\n`), with no file name. That's exactly what `parse error near '\n'` says: a redirection with nothing after it. The mistake was mine for writing placeholders in a form a shell treats as real syntax.

**The fix:** type the real numbers from the `--list` output, with no brackets. For example, `--list` prints something like this (your numbers will differ):

```
   0 BlackHole 2ch, Core Audio (2 in, 2 out)
>  1 MacBook Air Microphone, Core Audio (1 in, 0 out)
<  2 MacBook Air Speakers, Core Audio (0 in, 2 out)
   3 Call Output, Core Audio (0 in, 2 out)
```

In that case the command is:

```bash
python scripts/level_meter.py --mic 1 --call 0
```

One related trap: in step 1 I wrote `git remote -v   # should show...`. By default, interactive zsh doesn't treat `#` as the start of a comment. So that line can also fail, with git complaining about unknown arguments. Run just `git remote -v`. If the error came from a different line than the meter command, paste the exact line and I'll look again.

---

## What each M0 step does, and why

The goal of M0 is to prove the **foundation** works before any AI model is involved: both audio streams reach Python, cleanly and separately. If this layer is broken, nothing built on top of it can work, and an audio problem hidden inside an ASR test would be very hard to diagnose.

### Step 1 — Commit and push
- `git remote -v` shows where this local repo sends its history. It should list your GitHub URL twice, one line for fetch and one for push.
- `git add .` marks all new or changed files to go into the next snapshot. Our `.gitignore` is in place, so `.venv`, audio and weights are skipped automatically.
- `git commit -m "..."` saves that snapshot locally with a message.
- `git push` uploads the snapshot to GitHub.

Why now: the Tips say to commit after every working step, so there's always a known-good point to go back to.

### Step 2 — `brew install --cask blackhole-2ch`
- In Homebrew, a **cask** is a ready-made macOS package (an app or driver) rather than a command-line tool. This one contains the BlackHole driver.
- The driver is copied into a system folder for audio plug-ins (`/Library/Audio/Plug-Ins/HAL`). That's a system location, so macOS asks for your password.
- macOS's audio service only loads plug-ins when it **starts**. That's why BlackHole may not appear until you restart.

### Step 3 — The Multi-Output Device (Audio MIDI Setup)
This builds the "splitter" we discussed: one output that the call app plays into, which copies the sound to your headphones *and* to BlackHole.
- **Plug in the headphones first.** macOS only shows "External Headphones" while something is plugged in.
- **Primary Device = headphones.** The combined device follows one clock, and it should be the real hardware.
- **Drift Correction on BlackHole** keeps BlackHole's clock in step with the headphones', so there are no clicks after a few minutes.
- **Both at 48,000 Hz.** If the two run at different rates, macOS has to convert between them, which can cause glitches.
- **Rename to "Call Output"** so it's easy to recognise in device lists.

### Step 4 — Temporarily send system sound to "Call Output"
We need *some* sound to flow through BlackHole for the test, and a YouTube video is easiest. Setting the system output to Call Output sends the browser's sound into the splitter. Later, for real calls, we'll change only the call app's speaker setting and put the system output back to normal.

### Step 5 — The Python environment
- `python3 -m venv .venv` creates a folder `.venv` containing **its own copy of Python and pip**. Packages installed there don't affect the rest of your Mac, and the project's dependencies are written down and repeatable.
- `source .venv/bin/activate` changes **only the current Terminal window** so that `python` and `pip` mean the ones inside `.venv`. Your prompt then starts with `(.venv)`. **You need to repeat this in every new Terminal window.**
- `pip install -r requirements.txt` downloads the two packages listed:
  - **numpy** does fast maths on arrays of numbers, and audio *is* arrays of numbers;
  - **sounddevice** is the Python bridge to the Mac's audio system, and it ships with PortAudio built in.

### Step 6 — Run the meter
- `--list` prints every audio device with its number and how many input/output channels it has. `>` marks the default input and `<` the default output. You need two **inputs**: the microphone and BlackHole 2ch. "Call Output" shows `0 in` because it's an output only.
- The second command opens both inputs at once and draws the two bars.
- **The microphone permission prompt:** macOS controls which *apps* may record audio. The permission belongs to **Terminal**, not to Python. Without it, macOS gives the program pure zeros instead of an error. That's why the script checks for "only exact zeros" and tells you what to check.

### What the script does inside
- **`Meter` class:** one per device. It asks macOS for the device's details (name, sample rate, channels) and opens an input stream.
- **`_callback`:** macOS calls this on its own audio thread every few milliseconds with a new block of samples. It does two cheap calculations, average loudness (RMS, shown in decibels) and the loudest sample so far, and counts any "status" flags, which mean audio was dropped. The real capture module later will do even less here: just copy the block.
- **Main loop:** ten times a second it redraws one line with both bars. After 3 seconds it warns, once, if a device has given only zeros.
- **Ctrl+C** stops the loop, and the `finally` block always closes the streams cleanly.

### Step 7 — The three checks, and what each proves

| Check | Proves |
|---|---|
| Silence: MIC low, CALL empty | Both streams are open and the baseline is quiet |
| Speak: only MIC moves | The mic works, permission is granted, and your voice does **not** leak into the call lane |
| YouTube: only CALL moves, and you hear it | BlackHole receives the splitter's copy, and your headphones still play the sound |

The last two checks together prove the most important property of the system: **the two lanes are independent**. That's what lets us label the mic as "Me" without any analysis.

Run the corrected command and send me the `--list` output and what the three checks showed.

---

## 10. User — 2026-10-24 00:31

*Attachment: screenshot of Audio MIDI Setup — see [`session-01-assets/audio-midi-setup.png`](session-01-assets/audio-midi-setup.png)*

> to be more precise, here is my Audio MIDI Setup current state.

## 10. Claude

Thanks, the screenshot shows the setup exactly. Most of it is right, but there are two things to fix and one important discovery.

## What's already correct
- **"Call Output" exists** and is the current **system output**: the speaker icon 🔈 is next to it in the left list. That's what we want for the YouTube test.
- **BlackHole 2ch and TWS are ticked**, and MacBook Air Speakers is not. Sound goes to your earbuds and to BlackHole, not out of the laptop, so the mic can't pick up the call.
- **48 kHz** is set.
- Alert sounds go to **TWS 2** (the bell icon), not into Call Output. That's good: notification sounds won't end up in the transcript.

## Discovery: your headphones are Bluetooth, not wired

**"TWS"** stands for *True Wireless Stereo*, i.e. Bluetooth earbuds. macOS shows them as **two devices**:
- **TWS 1** is the earbuds' **microphone** (1 in / 0 outs);
- **TWS 2** is the earbuds' **speakers** (0 ins / 2 outs).

This works, but it brings one real risk. Bluetooth earbuds have two modes:
- **Listening mode (A2DP):** good stereo sound, but no microphone.
- **Headset mode (HFP):** turns on as soon as *any* app uses the earbuds' mic. Sound quality drops sharply, and on many earbuds the output device briefly disappears and comes back at a lower sample rate.

That's dangerous for us. The Multi-Output Device is built around TWS 2, so if it disappears or changes rate, the device can break in the middle of a call. Then you hear nothing and our program gets glitches.

The screenshot shows this trap is already set: the 🎤 icon next to **TWS 1** means the earbuds' mic is currently the **system default input**. Any app that uses the default mic (Zoom, Meet, Telegram) would switch your earbuds into headset mode.

**Fix A:** in System Settings → Sound → **Input**, choose **MacBook Air Microphone**. In the call app, also choose MacBook Air Microphone as the mic. The earbuds then stay in good listening mode the whole time. You'll still hear the call in your ears, so there's no echo problem.

## Fix B: the clock and drift-correction settings are reversed

- **Primary Device** is the **clock** the whole Multi-Output Device follows.
- **Drift Correction** is for the *other* devices, the ones that need to be kept in step with that clock.

Right now **BlackHole is the primary *and* has drift correction ticked**. Correcting the clock against itself does nothing useful, while TWS, the device that actually drifts, has no correction.

Earlier I said to make the headphones primary. **With Bluetooth earbuds, I'd change that advice.** Bluetooth devices can disconnect or switch modes. If the earbuds were the clock and they dropped out, the whole Multi-Output Device would lose its clock, and our capture would stall too. BlackHole is virtual and always present, so it's the more stable clock here. So:

- **Primary Device:** keep **BlackHole 2ch** (no change).
- **Drift Correction:** **untick BlackHole**, **tick TWS**.

## Optional: the BlackHole volume slider
The slider next to BlackHole (~75%) scales how loud the signal reaching our program is. Set it to **100%** so the program gets the full, unchanged level. Your own listening volume is then controlled in the call app or on the earbuds. As I mentioned before, the Mac's volume keys don't work on a Multi-Output Device.

## Then run the meter
With those changes, the two **inputs** for the meter are **MacBook Air Microphone** and **BlackHole 2ch**. Run `--list` to get their numbers and use them without angle brackets:

```bash
source .venv/bin/activate
python scripts/level_meter.py --list
python scripts/level_meter.py --mic 1 --call 0    # replace 1 and 0 with your numbers
```

**A question for the plan:** you said wired headphones earlier, but these are Bluetooth earbuds. Will you use these TWS earbuds in the interview, or wired ones? Both can work. Wired is simpler because it has no mode switching, but the TWS setup above works as long as the mic is always the MacBook's. I'll record the answer in `DECISIONS.md` (D0) and in the README setup section.

---

## 11. User — 2026-10-24 00:40

> I fixed everything. Also changed drift correction from BlackHole to TWS.
>
> I did not understand the problem with using bluetooth, wireless earbuds or headphones. Explain the problem in more understandable way

## 11. Claude

Good, with those fixes the clock setup is correct. Here's the Bluetooth issue in plainer terms.

## The core idea: Bluetooth is a narrow pipe

Think of the wireless connection between your Mac and the earbuds as a **narrow pipe** that can only carry a limited amount of sound data per second. Earbuds handle that limit by working in one of **two modes**:

| | 🎧 Music mode | 📞 Headset mode |
|---|---|---|
| What the pipe carries | Sound **to** your ears only | Sound to your ears **and** your voice back from the earbud mic |
| Sound quality | High, like music | Low, like an old phone line |
| Earbud microphone | **Off** | On |

In music mode, the whole pipe is used in one direction, so the sound is rich. In headset mode, the same pipe has to carry traffic **both ways**, so each direction gets only a small share and quality drops a lot, in both directions.

**The switch is automatic.** As soon as *any* app on the Mac starts using the **earbuds' microphone**, they jump from music mode to headset mode. You don't choose it; it just happens.

## Why that's a problem for us, specifically

**Problem 1: your voice would be recorded in poor quality.**
If the earbud mic were our "Me" microphone, the program would get your voice through headset mode: thin, compressed, telephone-like sound. Speech recognition on that is clearly worse, and Armenian recognition is already the hardest part of the project.

**Problem 2: the switch can break the audio setup in the middle of a call.**
Our "Call Output" device is a **group** that includes the earbuds' speaker device (TWS 2). When the earbuds change mode, macOS sees TWS 2 **disappear for a moment and come back as a different device**, with lower quality and a different format. A group whose member suddenly vanishes and changes can stop working properly. You might suddenly hear nothing, or hear crackling, and the program could miss pieces of what the other people said.

**What's *not* a problem:** the copy of the call that goes into BlackHole never travels over Bluetooth. It's copied inside the Mac, before the sound is sent to your ears. So even in headset mode, the *quality* of the call lane stays fine. The danger there is only the breakage in Problem 2.

## The fix you already made solves both

You set **MacBook Air Microphone** as the input. Now **nothing ever uses the earbud mic**, so the earbuds **stay in music mode** for the whole session:

- your voice is recorded by the Mac's good built-in mic, which fixes Problem 1;
- the earbuds never switch modes, so the Call Output group stays stable, which fixes Problem 2.

**One rule to remember:** in *every* app (Zoom, Meet, Telegram…), the microphone must be **MacBook Air Microphone**, never "TWS". Some apps pick the earbuds' mic on their own when they connect, so check the app's audio settings before the interview call.

**Two small leftovers, neither of which affects the program:**
- You hear the call with a short Bluetooth delay (about 0.2 s). That only affects your ears; the program's copy arrives without it.
- If the earbuds disconnect or the battery runs out, the group loses a member. Charge them before the interview. This is also why wired headphones are the slightly safer option, if you have some.

---

Next step: run the meter with the real device numbers and send me the `--list` output plus the three checks (silence, speaking, YouTube).

---

## 12. User — 2026-10-24 00:42

> Ok, but do we need to use headphone at all? The task specify microphone (check this part in the task file again and be sure about this).

## 12. Claude

I re-read the brief to check. You're right: **the brief does not require headphones.** That was my recommendation, not a requirement. Here's what the brief actually says on this, word for word:

> *"Capture the microphone and the system audio output (the other side of a call) at the same time."*
>
> *"On macOS this usually means a virtual loopback device such as BlackHole plus a Multi-Output Device, so the user still hears the call."*

And in **Out of scope**:

> *"echo handling (when the speakers are picked up by the microphone)"*

So the brief requires:
1. **A microphone** for your voice.
2. **System audio capture** (BlackHole) for the other side.
3. **A Multi-Output Device** so you can still hear the call. It doesn't say through what: headphones or laptop speakers are both fine.

The "out of scope" line even shows the authors **expect some people to use speakers**. They're telling you that you don't have to solve the echo that causes.

## So why did I recommend headphones?

"Out of scope" means **you don't have to fix it**. It doesn't mean **it won't happen**. With laptop speakers, this is what happens in the live demo:

1. Speaker 1 says "Բարև, ինչպե՞ս ես" and it plays out of the MacBook's speakers.
2. BlackHole captures it, and the program correctly prints **Speaker 1**.
3. **The mic also hears it from the speakers**, so the program prints it **again**, labelled **Me**.

Every sentence from the other side could then appear twice, once with the wrong speaker. The output gets confusing, and it adds load: twice as many segments in the queue, so higher latency.

One detail people often miss: Zoom and Meet have built-in echo cancellation, but it only cleans the audio *they send* to the other people. **Our program reads the raw microphone directly**, before any of that, so it gets no protection from it.

## Summary

| Option | Allowed by the brief? | Result in the demo |
|---|---|---|
| Laptop speakers | ✅ Yes (echo is out of scope) | Call speech also picked up by the mic → duplicates labelled "Me" |
| Earbuds/headphones (Mac's mic as input) | ✅ Yes | Clean: each sentence appears once, with the right label |

**My recommendation stays the same: use headphones for the interview**, because they give the cleanest result at zero cost in code. But it's **your choice**, and both are within the brief. If you go with speakers, we'll state the duplicate effect honestly in the README's limitations, which fits the brief's "honest about its limits" principle.

For the code, nothing changes either way: the program always reads **MacBook Air Microphone** and **BlackHole 2ch**. The only difference is which output device you tick in the Call Output group.

Which one do you want for the interview? I'll record it in `DECISIONS.md`. In the meantime the level-meter test can go ahead with your current earbud setup.

---

## 13. User — 2026-10-24 00:48

> Can't we just use my macbook's default microphone and speakers?

## 13. Claude

Yes, we can. It's fully allowed by the brief, and the program code doesn't change at all. Only the Call Output group changes.

## What to change in Audio MIDI Setup
In **Call Output**:
- **Untick TWS**, **tick MacBook Air Speakers**.
- **Primary Device:** keep **BlackHole 2ch**.
- **Drift Correction:** tick it for **MacBook Air Speakers** (the non-primary device).

Input stays **MacBook Air Microphone**, as now.

## What you gain and what you lose

| | MacBook mic + speakers | MacBook mic + earbuds |
|---|---|---|
| Setup | Simplest: nothing to connect or charge | Bluetooth must be connected and charged |
| Bluetooth mode-switch risk | None | Small (only if an app grabs the earbud mic) |
| **Echo:** call audio picked up by the mic | **Yes**: the other side's sentences can also appear as "Me" | No |
| Extra load on the program | More segments → more queue time | Normal |

**The one real cost is the echo.** On a MacBook Air the speakers and microphone are a few centimetres apart, so the mic will hear the call clearly. How badly it shows up depends on the volume:
- **Low speaker volume:** the echo is quiet, and the VAD may ignore most of it.
- **Normal or high volume:** expect many call sentences duplicated as "Me".

## If we go this way

1. **We don't fix the echo now.** The brief puts it out of scope, and the Tips say to build the core first.
2. **We measure it**, with a test call on speakers and a count of how many duplicate "Me" lines appear.
3. **If time is left in M5**, there's a simple, honest improvement: while the call lane is active, **ignore mic segments that overlap it in time**. It's cheap, but it has a trade-off: if you really talk over someone, your words get dropped too. It would go in `DECISIONS.md` with that trade-off stated.
4. **The README states the limitation plainly**: "with laptop speakers, call audio leaks into the microphone and may be transcribed twice".

## My honest view
For **development and testing**, speakers are perfectly fine and easiest. For **the interview demo**, headphones give the cleanest output with no extra work. One practical approach is to **develop with speakers and decide for the interview later**, once we've measured how bad the echo really is on your Mac. Then the choice rests on numbers, which matches Tip 5.

Shall I record it that way in `DECISIONS.md`: speakers for development, interview choice decided after the echo measurement? After that, the next step is still the level-meter test. With speakers, check that the CALL bar moves when YouTube plays. The MIC bar will move a little too, and that's exactly the echo we'll measure later.

---

## 14. User — 2026-10-24 00:50

> Ok, then fix the code so it will work with my default, standard microphone and speakers, then if everything work correctly at the end, we will come to this. So fix the code and let me know what you changed

## 14. Claude

Before changing anything, I checked what actually needs to change. **The code doesn't need any change.** The only change is the audio setup you're making in Audio MIDI Setup.

## Why the code already works with your MacBook's mic and speakers

The level meter, and the real program later, only ever **reads two inputs**:

1. **MacBook Air Microphone**: your voice.
2. **BlackHole 2ch**: the copy of the call audio.

It never touches the **output** side. Whether you hear the call through the earbuds or the MacBook speakers is decided entirely by which device is ticked in the **Call Output** group. Python never sees that choice. The commands stay the same:

```bash
python scripts/level_meter.py --list
python scripts/level_meter.py --mic <number of MacBook Air Microphone> --call <number of BlackHole 2ch>
```

(Remember to type the numbers without the angle brackets.)

If I changed the code anyway, it would be a change for its own sake. The Tips warn against exactly that (Tip 8: keep it simple, don't let the AI add things that aren't needed).

## What I did change: the decision log

I'm recording your choice in `DECISIONS.md`, so a future chat (or the interviewer) can see it:

*[Tool activity] Edited entry D0 in `DECISIONS.md` (audio devices: MacBook Air Microphone in; MacBook Air Speakers out via Call Output with BlackHole as primary/clock and drift correction on the speakers; Bluetooth earbuds set aside and why; echo consequence to be measured before choosing the interview setup) and copied it into the repo.*

I left the code unchanged. The only file I updated is **`DECISIONS.md`**, where entry **D0** now records:
- the audio choice: MacBook mic in, MacBook speakers out through Call Output, with BlackHole as the clock and drift correction on the speakers;
- why Bluetooth earbuds were set aside for now;
- the known echo effect, and that the interview setup will be decided after we measure how often the echo happens.

## Your setup steps
1. In **Call Output**, untick **TWS**, tick **MacBook Air Speakers**, and tick **Drift Correction** for MacBook Air Speakers. Keep **BlackHole 2ch** as the Primary Device.
2. Check that System Settings → Sound: **Output** is **Call Output** and **Input** is **MacBook Air Microphone**.

## The test, adjusted for speakers

| Action | MIC bar | CALL bar | You hear |
|---|---|---|---|
| Stay silent | low | empty | — |
| Speak | **moves** | stays empty | — |
| Play YouTube | **moves a little** (this is the echo) | **moves** | video from the speakers |

The key check is the second row. When you speak, the **CALL bar must stay empty**. That proves your voice never enters the call lane, and it's the property the "Me" label depends on.

## One optional improvement (only if you want it)
Device **numbers can change** when devices connect or disconnect. For example, your earbuds showing up as TWS 1 and TWS 2 shifts the numbering. Later I could let the program accept a **name** instead, like `--mic "MacBook Air Microphone" --call "BlackHole"`, failing loudly if no device or more than one matches. It's a small reliability gain for the interview. I'd suggest it when we build the real `audio/devices.py` module in M1, not now.

Commit when you're ready (`git add DECISIONS.md && git commit -m "Record audio device decision"`), then send me the `--list` output and the results of the three checks.

---

## 15. User — 2026-10-24 01:00

> Perfect. Now everything is clear.
>
> Just to be sure that I understood Blackhole and what it's for, now I'll explain it to you and you should tell me if everything is correct or not.
>
> BlackHole is a virtual audio driver, which takes all system audio (this could include microphone, videos' sounds, any speakers in the call, etc.) and direct it to wherever we need. Correct?

## 15. Claude

You're **partly right**. The core is correct, but two details are off, and they matter for understanding our setup.

## ✅ Correct
**"BlackHole is a virtual audio driver."** Yes, exactly. It's software that pretends to be a sound card, with no hardware behind it.

## ❌ Detail 1: it doesn't *take* audio by itself
BlackHole doesn't go out and collect anything. It's **passive**: it only contains what is **sent into it**. If nothing is routed to its output side, it's silent.

In our setup, sound reaches it only because **we routed it there**. The system output (or later just the call app) plays into **Call Output**, and that group copies the sound into BlackHole. Without that routing, BlackHole would stay empty even while a video plays.

## ❌ Detail 2: the microphone is *not* part of it
This is the important one. The **microphone is a completely separate device** and never goes through BlackHole in our setup. BlackHole carries only **sound that the Mac plays**: call voices, videos, whatever is sent to Call Output.

That separation is exactly what the design relies on:
- **MacBook Air Microphone** → only *your* voice → label "Me"
- **BlackHole 2ch** → only what the Mac *plays* (the call) → "Speaker 1, 2…"

If the mic were mixed into BlackHole, we couldn't tell you apart from the others. (With speakers, the mic can *hear* the call through the air, but that's the echo issue, which works the other way round: call sound leaking into the mic lane.)

## ❌ Detail 3 (small): it doesn't *direct* sound anywhere
BlackHole doesn't route or forward anything. It's a **loop**: what goes into its output side comes straight back out of its input side, and **whoever opens that input** reads it. In our case, that's our Python program.

The **directing** is done by other things:
- **macOS Sound settings / the call app's speaker setting** decide what plays into Call Output;
- the **Multi-Output Device (Call Output)** splits the sound to the speakers and to BlackHole.

## Corrected version in one sentence
> **BlackHole is a virtual audio cable: sound that the Mac plays into it comes straight back out as an input that other programs, like ours, can record. It carries only the audio we route into it (here, the call via the Multi-Output Device) and never the microphone, which is a separate input.**

If that matches how you see it now, send me the `--list` output and the three check results, and we'll close milestone M0.

---

## 16. User — 2026-10-24 01:08

> Ok, explain Blackhole completely from the beginning to the end, in very more details, so I can understand how does it work

## 16. Claude

Here's BlackHole explained from the ground up, in layers. Each part builds on the one before it.

---

## Part 1 — What "sound" is inside a computer

A microphone measures **air pressure** many times per second. Each measurement is one number, called a **sample**:

- **Sample rate** = how many measurements per second. **48,000 Hz** means 48,000 numbers every second.
- **Channels** = how many separate streams. **Stereo = 2** (left and right), so 96,000 numbers per second.
- **Sample format**: on macOS each number is usually a **32-bit float** between −1.0 and +1.0, where 0 is silence.

Playing sound is the same thing in reverse: the computer sends numbers to the speaker, which turns them back into air pressure.

**Key point:** to a computer, audio is just a **long, steady stream of numbers that must arrive on time.** Every idea below is about moving that stream from one place to another without gaps.

## Part 2 — How macOS moves audio: Core Audio

Apps don't talk to sound cards directly. Everything goes through **Core Audio**, Apple's audio system. It's built in layers:

```
  Apps (Zoom, Chrome, our Python program)
        │   "here are my samples" / "give me samples"
        ▼
  Core Audio  — runs in a background system process (coreaudiod)
        │   mixes, converts, keeps time
        ▼
  HAL = Hardware Abstraction Layer — a uniform "device" interface
        │
        ▼
  Drivers — one per device; each knows how to talk to its hardware
        │
        ▼
  Hardware — MacBook speakers, microphone, USB/Bluetooth chips
```

### The "device" idea
The HAL turns every driver into a uniform **device** with standard properties: a name, input channels, output channels, supported sample rates, and a **clock**. Apps only see devices. They never know (or care) what's behind them. **This is the loophole BlackHole uses:** if you write a driver that behaves like a device, every app treats it as one, even with no hardware behind it.

### The IO cycle: how audio actually moves
Core Audio doesn't move samples one at a time. It works in **small blocks** on a regular beat, called the **IO cycle**:

- Every few milliseconds (for example every 512 samples ≈ **10.7 ms** at 48 kHz), Core Audio wakes up.
- For **output** devices, it asks every app playing to that device for its next block, **adds them together** (mixing), and hands the mixed block to the driver.
- For **input** devices, it gets the newest block from the driver and hands a copy to every app that is recording from it.

This beat never stops while a device is in use. If an app is too slow to provide or take its block in time, you get a click or gap. That's what our level meter counts as a "dropout".

### The clock
What decides *when* each beat happens? The **device's clock**. A real sound card has a tiny crystal oscillator that ticks exactly 48,000 times a second, or as close as physics allows. Every device has its own crystal, so no two are perfectly equal. Remember this; it comes back in Part 5.

## Part 3 — The gap BlackHole fills

With this design:
- **Output devices are dead ends.** Samples go in and become sound, and no app can read them back.
- **Input devices only offer what their hardware records.**

So there's **no device whose input is "what the Mac is playing"**. Our Python program can open any *input* device, but none of them carries the call. macOS has no built-in "record what's playing" device.

## Part 4 — What BlackHole is, exactly

**BlackHole is a driver with no hardware.** It's an **Audio Server Plug-in**, the official Apple format for audio drivers that run *inside* the Core Audio process. When installed, it registers one device, "BlackHole 2ch", that has:

- **2 output channels** (apps can play into it), and
- **2 input channels** (apps can record from it).

A real sound card connects its output to a speaker chip and its input to a microphone chip. **BlackHole connects its own output to its own input.** That's the whole trick: a **virtual cable** with both ends plugged into the same device.

It's free and open-source, made by Existential Audio. Installing it (`brew install --cask blackhole-2ch`) copies a file called `BlackHole.driver` into the system folder where Core Audio looks for plug-ins. Core Audio loads plug-ins **when it starts**, which is why a restart is sometimes needed before "BlackHole 2ch" appears.

### Inside: the ring buffer
How does the output connect to the input? Through a **ring buffer**: a fixed-size row of memory slots that gets reused in a circle.

*[Diagram: "BlackHole ring buffer". A row of 12 memory slots. Slots 5–9 are filled ("written, not yet read"); the others are free ("old, already read"). An arrow from above marks the "Write position (output side)" just after the filled slots; an arrow from below marks the "Read position (input side)" at the first filled slot. Caption: "↻ after the last slot, both positions wrap back to the first".]*

Step by step:

1. **Output side (writing):** on each IO cycle, Core Audio gives BlackHole the mixed block of samples being "played" into it. BlackHole writes that block into the next slots and moves the **write position** forward.
2. **Input side (reading):** on each IO cycle, for anyone recording from BlackHole, Core Audio asks for the next block. BlackHole copies it out from the **read position**, just behind the write position, and moves that forward.
3. **Wrapping:** when either position reaches the end of the row, it jumps back to the start, overwriting slots that were already read. The memory is reused forever.

Because writing and reading happen on the **same device with the same clock**, the two positions move at exactly the same speed. They never overtake each other, and the gap stays tiny. That's why BlackHole adds essentially no delay.

### Consequences of this design (they explain real behaviour)

| Situation | What happens inside | What you notice |
|---|---|---|
| Nothing plays into BlackHole | No new samples written | Our program reads **exact zeros**: total silence |
| Two apps play into it at once | Core Audio **mixes** (adds) them before BlackHole sees them | Recording contains both, mixed; BlackHole can't separate them |
| Nobody records from it | Samples are written and later overwritten | Nothing; that's fine |
| Several apps record from it | Each gets its own copy of the same block | All see identical audio |
| Something plays into it at 75% volume | Samples are scaled down before writing | Our program gets a quieter signal |

BlackHole never changes the numbers otherwise: no compression, no filtering, no noise. **Bit-perfect**: what goes in is what comes out.

### What BlackHole does *not* do
- It doesn't **capture** anything on its own; it only holds what is played into it.
- It doesn't **route** or **forward**; it's one cable, not a switchboard.
- It doesn't know **which app** a sound came from; everything played into it is mixed together.
- It doesn't **record to a file**; that's the job of whatever reads its input (our program).
- It doesn't involve the **microphone** at all.

## Part 5 — Why BlackHole alone isn't enough: the Multi-Output Device

If the call app plays into BlackHole only, the call goes **into the cable and nowhere else**. Our program hears it; you don't. That's where the name "BlackHole" comes from.

The **Multi-Output Device** ("Call Output") solves this. It's another kind of virtual device, built into macOS, that **copies one output to several devices**:

```
Call app ──► Call Output ──┬──► MacBook Air Speakers  (you hear it)
                           └──► BlackHole 2ch          (our program records it)
```

On each IO cycle, Core Audio takes the block the call app played into Call Output and **sends the same block to both devices**.

### Back to clocks: Primary Device and Drift Correction
The speakers have a real crystal clock. BlackHole has **no crystal at all**; it generates its beat from the Mac's general system timer. Two clocks never tick at exactly the same speed. Even a 0.001% difference adds up: after 10 minutes, one device has consumed about 30 samples more than the other.

- **Primary Device** = the clock that Call Output follows. We chose **BlackHole**, because it's always present.
- **Drift Correction** on the **other** device (the speakers) = Core Audio **resamples very slightly** (stretches or squeezes the stream by tiny amounts) so the speakers stay in step with the primary clock. Without it, the speakers would slowly run ahead or behind, until a buffer runs empty or overflows and you hear a click.

## Part 6 — The full journey of one 10 ms piece of the call

Speaker 1 says "Բարև". Here's what happens to one tiny slice of it:

1. **Their computer** records it, compresses it and sends it over the internet as packets.
2. **Your call app** receives the packets, decodes them back into samples, and **plays** them into its speaker device, **Call Output**.
3. **Core Audio (IO cycle)** mixes everything playing into Call Output into one block and sends a copy to each member device.
4. **Speakers path:** the MacBook speakers' driver gives the block to the speaker hardware, and you hear "Բարև".
5. **BlackHole path:** BlackHole's driver **writes** the block into its ring buffer.
6. **Core Audio (input side)** notices our Python program is recording from BlackHole 2ch. On the next IO cycle it asks BlackHole for a block, and BlackHole **reads** it from the ring buffer.
7. **PortAudio / sounddevice** receive that block and call our **callback** with it as a NumPy array of floats.
8. **Our program** now has the samples, and the rest of the pipeline (VAD, ASR, translation) takes over.

Steps 3 to 7 take a few milliseconds. The call audio reaches our program **at about the same moment you hear it**.

Meanwhile, completely separately, the **MacBook Air Microphone** follows its own path straight into our program's second stream: microphone hardware → its driver → Core Audio → our mic callback. **The two paths never touch.**

## Part 7 — The whole thing in one picture

> **Core Audio treats any driver as a device. BlackHole is a driver with no hardware: its output is connected to its own input through a ring buffer, so audio played into it immediately comes back out as an input a program can record. The Multi-Output Device copies the call into both the speakers (for you) and BlackHole (for us). Our program then records two separate inputs: the microphone (you) and BlackHole (everyone else).**

If any part is unclear, tell me which one: the IO cycle, the ring buffer, the clocks, or the journey. Otherwise, the next step is still the level-meter test.

---

## 17. User — 2026-10-24 22:29

> So as I understand, Blackhole is a virtual driver inside Core Audio, which let us to route our internal sounds. Because our python program by default does not has access to Macbook's internal sounds, BlackHole sits in the middle, takes the internal sound and route it to our python program. Did I get it correct?

## 17. Claude

Yes, that's essentially correct. Two small precisions make it exact:

1. **"takes the internal sound"** → more precisely, it **receives only the sound we send into it**. BlackHole doesn't grab sound by itself. Our routing (system or call-app output → Call Output → BlackHole) is what puts the call into it.
2. **"routes it to our Python program"** → more precisely, it **offers that sound as an input device**, and our program **opens that input** and reads from it. BlackHole doesn't push anything to us. It's like a cable end lying there, and our program plugs into it.

Your sentence with those two tweaks:

> BlackHole is a virtual driver inside Core Audio. Our Python program can't normally hear the Mac's internal sound, because no input device carries it. Sound we route into BlackHole comes back out of it as an input device, which our program opens and records.

Everything else (virtual driver, inside Core Audio, the reason it's needed) is exactly right. You've got it.

Next step: run the level meter and send me the `--list` output plus the three checks (silence, speaking, YouTube).

---

## 18. User — 2026-10-24 22:48

> Yess, perfect, got it.
>
> Now let's create the handout of this chat as .md file (exactly how it explained in the file) in chats/ folder. I also need to change the chat and keep the information of all this. So let me know how can I do it without loosing any information.

## 18. Claude

I'll write the handover file first. Then I'll check how chats can be exported, so you get accurate steps rather than a guess.

*[Tool activity]*
- Web search for exporting a single Claude conversation as Markdown (no official support article found; third-party exporters listed).
- Wrote `chats/handover-01.md` (goal, current state, decisions, how we work, next step) and copied it into the repo.

I couldn't find an official way to export a single chat, so I won't guess at the app's menus. First, the handover file.

I've added **`chats/handover-01.md`** to your repo, written in the format from Tip 6: **goal, current state, decisions, next step**. I added one more section, **"How we work"**, with your preferences: step by step, explain before fixing, no `< >` placeholders, and you run the commands. A new chat would otherwise not know these.

## How to switch chats without losing anything

There are **two different things** here, and you need both:

| | Handover (`handover-01.md`) | Chat export |
|---|---|---|
| What | A short summary to **start the next chat** | The **full, unedited** conversation |
| Who needs it | The next chat (me, starting fresh) | The **evaluators** (brief, deliverable 3) |
| Replaces the other? | **No** | **No** |

### 1. Keep this chat; never delete it
The brief says the interviewers will open **the original conversations in the app**, not only the exported copies. Leave this chat as it is. You can also come back to it to look something up, as Tip 6 suggests.

### 2. Export this chat into `chats/`
The brief requires every session as its own Markdown file, in full and unedited. I **can't export this conversation from inside it**, and I couldn't find an official one-chat Markdown export to point you to, so I won't guess at the menus. Check the chat's menu in the app, or search [support.claude.com](https://support.claude.com) for "export conversation". Third-party exporters also exist, such as [Claude Exporter for Chrome](https://chromewebstore.google.com/detail/hebhnhibdecijopliikejmojkpkcelbc) and [claude-chat-exporter](https://github.com/agarwalvishal/claude-chat-exporter). I haven't tested them, so if you use one, check that the file contains **every message** before relying on it. Save it as something like `chats/session-01-understanding-and-setup.md`.

Doing this now is safer than waiting until the end, when it's easy to forget a session.

### 3. Commit
```bash
cd ~/Desktop/armenian-transcriber
git add chats/handover-01.md DECISIONS.md
git commit -m "Add handover for session 1"
git push
```

### 4. Start the new chat
- Connect the **same folder** (`armenian-transcriber`) to the new chat.
- Your first message can be: *"Read chats/handover-01.md, PLAN.md and DECISIONS.md, then continue with the next step."*

Everything important lives **in the repo**, not in chat memory, so the new chat starts with the same knowledge. That's the point of Tip 7.

One small naming point: the brief uses `chats/` for exported transcripts. Keeping the handover there is fine, because its name and first lines say clearly that it's a summary, not an export. If you'd rather keep `chats/` for exports only, move it to `docs/handover-01.md`.

---

## 19. User — 2026-11-01 01:34

> sorry, I was wrong, not a handover. You need to export this chat as a handout in chats/ folder

## 19. Claude

*[Tool activity] Copied the two attached screenshots into `chats/session-01-assets/`; wrote this file, `chats/session-01-understanding-research-setup.md`, and copied it into the repo.*

*(Claude's reply to this message follows this export in the app: it reports what was written, explains what is verbatim and what is summarised, and gives the commit commands.)*
