"""Render Lamplight Pay demo video v3 (1280x720, narrated).

Terminal-style frames built with PIL from the real `scripts/demo.py` output
(fresh run Oct 27, 2026 — eth-tester is deterministic, so addresses and the
release/refund/dispute tx hashes match the v2 video), assembled with ffmpeg.
Narration: gTTS segments (build/demo-video-v3-audio/*.mp3, durations in
durations.json), mixed in with adelay so each segment starts 0.6s into its
section. On-screen caption bars carry the narration text.
Output: build/demo-video-v3.mp4
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
FRAMES_DIR = ROOT / "build" / "demo-video-v3-frames"
AUDIO_DIR = ROOT / "build" / "demo-video-v3-audio"
FRAMES_DIR.mkdir(parents=True, exist_ok=True)

W, H = 1280, 720
BG = (13, 17, 23)
FG = (230, 237, 243)
GREEN = (63, 185, 80)
BLUE = (88, 166, 255)
GOLD = (210, 153, 34)
MUTED = (139, 148, 158)
BAR = (8, 11, 16)

MONO = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 22)
MONO_BIG = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 34)
MONO_TITLE = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 44)
SANS = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)

NARR = {
    "title": ("Lamplight Pay. Escrowed settlement for agent to agent work, on HSK Chain. "
              "One agent hires another. The funds are locked on chain, delivery is proven "
              "by a hash, and both sides keep a receipt. It is a minimal, auditable "
              "settlement layer. No trading, no real money. Just escrow and receipts."),
    "demo_a": ("This is the real demo, running on a local EVM. Every job starts with a "
               "priced quote both sides can prove they agreed to. Scenario A: a fifty "
               "token job. The payer funds it, the agent accepts, delivers, and the payer "
               "releases. The agent is paid fifty test tokens."),
    "demo_b": ("Scenario B: a twenty token job where the agent never delivers. Once the "
               "deadline passes, the payer reclaims the funds. Nothing is lost."),
    "demo_c": ("Scenario C: the payer disputes a delivery, then resolves it in the "
               "agent's favour. And a stranger trying to release someone else's funds is "
               "rejected. The contract reverts. Each scenario writes a receipt, with the "
               "real transaction hash as proof. After all three, the escrow holds zero. "
               "The contract never keeps funds."),
    "testnet": ("The same contracts are deployed live on HSK Chain testnet, chain one "
                "three three. Agent escrow, and Mock U S D C. A test token, not real money. "
                "You can verify both on the testnet explorer."),
    "closing": ("The code and the receipts are in the public repo, and the project is "
                "submitted to the HSK Chain Horizon hackathon on DoraHacks. The escrow "
                "balance after every scenario is zero. The contract never keeps funds. "
                "No real funds move anywhere in this build."),
}
# Caption text mirrors the narration, except "Mock U S D C" is written as
# "MockUSDC" on screen so it does not wrap letter-by-letter mid-word.
CAPTIONS = {k: v.replace("Mock U S D C", "MockUSDC") for k, v in NARR.items()}
DUR = json.loads((AUDIO_DIR / "durations.json").read_text())
LEAD = 0.6  # narration starts this far into each section


def short(tx: str) -> str:
    return tx[:10] + "…" + tx[-6:]


def wrap(text: str, font, max_w: int):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if font.getlength(trial) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def render(lines, caption: str, path: pathlib.Path):
    """lines: list of (text, color, font). caption: narration text for the bar."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    y = 56
    for text, color, font in lines:
        d.text((70, y), text, fill=color, font=font)
        y += 46 if font is MONO else 62
    cap_lines = wrap(caption, SANS, W - 140)
    bar_h = 16 + len(cap_lines) * 27 + 16
    d.rectangle([0, H - bar_h, W, H], fill=BAR)
    d.line([0, H - bar_h, W, H - bar_h], fill=(48, 54, 61), width=2)
    cy = H - bar_h + 16
    for line in cap_lines:
        d.text((70, cy), line, fill=FG, font=SANS)
        cy += 27
    img.save(path)


TITLE = [
    ("Lamplight Pay", GOLD, MONO_TITLE),
    ("", FG, MONO),
    ("Escrowed settlement for agent-to-agent work", FG, MONO_BIG),
    ("on HSK Chain", FG, MONO_BIG),
    ("", FG, MONO),
    ("HSK Chain Horizon Hackathon  ·  Agent Payments & A2A Settlement", MUTED, MONO),
]

PAGE_A = [
    ("$ python scripts/demo.py  —  local EVM demo", GOLD, MONO),
    ("MockUSDC deployed:   0xF2E246BB…55De395b", FG, MONO),
    ("AgentEscrow deployed: 0x2946259E…1BeD384", FG, MONO),
    ("", FG, MONO),
    ("[A] quote: holder audit, 50 mUSDC, hash-stable", FG, MONO),
    ("[A] job 0 funded, tx " + short("c671620b3063dee1ef538c46c429d0dd9400b85098b80d62636633e564280fbf"), FG, MONO),
    ("[A] RELEASED, tx " + short("99a6f95511a5ccb97776412e9e9f5b8c8c5981be6f51a972fcee4ea9142dde44"), GREEN, MONO),
    ("[A] agent mUSDC balance: 50.0", FG, MONO),
]

PAGE_B = [
    ("$ python scripts/demo.py  —  continued", GOLD, MONO),
    ("[B] job 1 funded (20 mUSDC), agent never delivers", FG, MONO),
    ("[B] REFUNDED after deadline", GREEN, MONO),
]

PAGE_C = [
    ("$ python scripts/demo.py  —  continued", GOLD, MONO),
    ("[C] job 2 disputed by payer after delivery", FG, MONO),
    ("[C] dispute resolved TO AGENT", GREEN, MONO),
    ("", FG, MONO),
    ("[guard] stranger release correctly reverted", GREEN, MONO),
    ("", FG, MONO),
    ("Final balances (mUSDC): payer=9920.0 agent=80.0 escrow=0.0", BLUE, MONO),
    ("All three scenarios passed.", GREEN, MONO),
]

TESTNET = [
    ("Live on HSKChain Testnet (chain 133)", GOLD, MONO_BIG),
    ("", FG, MONO),
    ("AgentEscrow  0x6Fa3d30F854aCBd589E10D78e9531fB910759eb7", FG, MONO),
    ("MockUSDC     0x860CadF955CF73FDB8E9ED2979104baae9f833B9", FG, MONO),
    ("Deployer     0xa67d284fC85345c2e3aCC3A34d46f93a295df341", FG, MONO),
    ("", FG, MONO),
    ("Verify: testnet-explorer.hskchain.net", BLUE, MONO),
]

CLOSING = [
    ("github.com/queenellis2026-hash/lamplight-pay-hsk", BLUE, MONO_BIG),
    ("", FG, MONO),
    ("dorahacks.io/build/50417", BLUE, MONO_BIG),
    ("", FG, MONO),
    ("Escrow balance after every scenario: 0", GREEN, MONO_BIG),
    ("The contract never keeps funds.", FG, MONO_BIG),
]

# (key, lines, accumulate?, tail_s) — section duration = max(LEAD + narr + tail, lines*step)
SECTIONS = [
    ("title", TITLE, False, 0.5),
    ("demo_a", PAGE_A, True, 0.5),
    ("demo_b", PAGE_B, True, 0.5),
    ("demo_c", PAGE_C, True, 0.5),
    ("testnet", TESTNET, False, 1.0),
    ("closing", CLOSING, False, 2.0),
]
STEP = 1.0  # seconds between accumulated terminal lines

concat_entries = []  # (frame path, duration)
section_starts = {}
t = 0.0
n = 0
for key, lines, accum, tail in SECTIONS:
    section_starts[key] = t
    dur = max(LEAD + DUR[key] + tail, len(lines) * STEP if accum else 0.0)
    if accum:
        for k in range(len(lines)):
            p = FRAMES_DIR / f"f{n:04d}.png"
            render(lines[: k + 1], CAPTIONS[key], p)
            d = STEP if k < len(lines) - 1 else dur - (len(lines) - 1) * STEP
            concat_entries.append((p, d))
            n += 1
    else:
        p = FRAMES_DIR / f"f{n:04d}.png"
        render(lines, CAPTIONS[key], p)
        concat_entries.append((p, dur))
        n += 1
    t += dur

total = t
print(f"sections: { {k: round(v, 2) for k, v in section_starts.items()} }")
print(f"total video: {total:.2f}s ({total/60:.2f} min), {len(concat_entries)} unique frames")

# concat list (repeat last frame with no duration, per ffmpeg concat rules)
lst = FRAMES_DIR / "concat.txt"
with lst.open("w") as f:
    for p, d in concat_entries:
        f.write(f"file '{p}'\nduration {d:.3f}\n")
    f.write(f"file '{concat_entries[-1][0]}'\n")

silent = ROOT / "build" / "demo-video-v3-silent.mp4"
subprocess.run(
    ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
     "-vf", "fps=30", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
     "-movflags", "+faststart", str(silent)],
    check=True, capture_output=True, text=True)

# audio: convert segments to 48k mono wav, delay each to its section start + LEAD, mix
wavs, delays = [], []
for i, (key, *_rest) in enumerate(SECTIONS):
    wav = AUDIO_DIR / f"{key}.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(AUDIO_DIR / f"{key}.mp3"),
                    "-ar", "48000", "-ac", "1", str(wav)],
                   check=True)
    wavs.append(wav)
    delays.append(int(round((section_starts[key] + LEAD) * 1000)))

filt = "".join(f"[{i}:a]adelay={d}|{d}[a{i}];" for i, d in enumerate(delays))
filt += "".join(f"[a{i}]" for i in range(len(wavs))) + f"amix=inputs={len(wavs)}:normalize=0[aout]"
audio = AUDIO_DIR / "mixed.m4a"
cmd = ["ffmpeg", "-y"]
for w in wavs:
    cmd += ["-i", str(w)]
cmd += ["-filter_complex", filt, "-map", "[aout]", "-c:a", "aac", "-b:a", "128k", str(audio)]
subprocess.run(cmd, check=True, capture_output=True, text=True)

out = ROOT / "build" / "demo-video-v3.mp4"
subprocess.run(
    ["ffmpeg", "-y", "-i", str(silent), "-i", str(audio),
     "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy",
     "-t", f"{total:.2f}", str(out)],
    check=True, capture_output=True, text=True)

(ROOT / "build" / "demo-video-v3-narration.txt").write_text(
    "\n\n".join(f"[{k.upper()}]\n{v}" for k, v in NARR.items()) + "\n")
print(f"wrote {out}")
