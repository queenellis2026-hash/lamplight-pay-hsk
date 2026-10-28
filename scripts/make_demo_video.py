"""Render the Lamplight Pay demo as a simple 1280x720 mp4.

Terminal-style frames built with PIL from the real `scripts/demo.py` output
(shortened tx hashes for readability; full hashes live in demo-receipts/),
assembled with ffmpeg. No audio track — captions carry the story.
Output: build/demo-video.mp4
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "build" / "demo-video-frames"
OUT_DIR.mkdir(parents=True, exist_ok=True)

W, H = 1280, 720
BG = (13, 17, 23)
FG = (230, 237, 243)
GREEN = (63, 185, 80)
BLUE = (88, 166, 255)
GOLD = (210, 153, 34)
MUTED = (139, 148, 158)

try:
    MONO = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 22)
    MONO_BIG = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 34)
    MONO_TITLE = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 44)
except OSError:
    MONO = ImageFont.load_default()
    MONO_BIG = MONO
    MONO_TITLE = MONO


def frame(lines, path):
    """lines: list of (text, color, font)."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    y = 60
    for text, color, font in lines:
        d.text((70, y), text, fill=color, font=font)
        y += 46 if font is MONO else 62
    img.save(path)


def short(tx: str) -> str:
    return tx[:10] + "…" + tx[-6:]


DEMO_PAGE_1 = [
    ("$ python scripts/demo.py  —  local EVM demo", GOLD),
    ("MockUSDC deployed:   0xF2E246BB…55De395b", FG),
    ("AgentEscrow deployed: 0x2946259E…1BeD384", FG),
    ("", FG),
    ("[A] job 0 funded, tx " + short("6db35ed48c50ab12701834307b8aa09176dce208b6aeb9c72e4c661bb8a8205f"), FG),
    ("[A] RELEASED, tx " + short("99a6f95511a5ccb97776412e9e9f5b8c8c5981be6f51a972fcee4ea9142dde44"), GREEN),
    ("[A] agent mUSDC balance: 50.0", FG),
    ("", FG),
    ("[B] job 1 funded (20 mUSDC), agent never delivers", FG),
    ("[B] REFUNDED after deadline", GREEN),
]

DEMO_PAGE_2 = [
    ("$ python scripts/demo.py  —  continued", GOLD),
    ("[C] job 2 disputed by payer after delivery", FG),
    ("[C] dispute resolved TO AGENT", GREEN),
    ("", FG),
    ("[guard] stranger release correctly reverted", GREEN),
    ("", FG),
    ("Final balances (mUSDC): payer=9920.0 agent=80.0 escrow=0.0", BLUE),
    ("All three scenarios passed.", GREEN),
]

frames = []
n = 0


def add(lines, hold_frames=3):
    global n
    for _ in range(hold_frames):
        p = OUT_DIR / f"f{n:04d}.png"
        frame(lines, p)
        frames.append(p)
        n += 1


# Title card (holds ~4s at 30fps -> 120 frames, use 90)
title = [
    ("Lamplight Pay", GOLD, MONO_TITLE),
    ("", FG, MONO),
    ("Escrowed settlement for agent-to-agent work", FG, MONO_BIG),
    ("on HSK Chain", FG, MONO_BIG),
    ("", FG, MONO),
    ("HSK Chain Horizon Hackathon  ·  Agent Payments & A2A Settlement", MUTED, MONO),
]
for _ in range(90):
    p = OUT_DIR / f"f{n:04d}.png"
    frame(title, p)
    frames.append(p)
    n += 1

# Demo output, lines accumulate — split across two screens so nothing
# runs off the bottom of the 720px frame (the old single-screen cut
# the [guard] and final-balances lines off entirely).
for page in (DEMO_PAGE_1, DEMO_PAGE_2):
    shown = []
    for text, color in page:
        shown.append((text, color, MONO))
        # re-render whole accumulated screen each step, hold ~1s per line
        for _ in range(30):
            p = OUT_DIR / f"f{n:04d}.png"
            frame(shown, p)
            frames.append(p)
            n += 1

# Testnet card
testnet = [
    ("Live on HSKChain Testnet (chain 133)", GOLD, MONO_BIG),
    ("", FG, MONO),
    ("AgentEscrow  0x6Fa3d30F854aCBd589E10D78e9531fB910759eb7", FG, MONO),
    ("MockUSDC     0x860CadF955CF73FDB8E9ED2979104baae9f833B9", FG, MONO),
    ("Deployer     0xa67d284fC85345c2e3aCC3A34d46f93a295df341", FG, MONO),
    ("", FG, MONO),
    ("Verify: testnet-explorer.hskchain.net", BLUE, MONO),
]
for _ in range(120):
    p = OUT_DIR / f"f{n:04d}.png"
    frame(testnet, p)
    frames.append(p)
    n += 1

# End card
end = [
    ("github.com/queenellis2026-hash/lamplight-pay-hsk", BLUE, MONO_BIG),
    ("", FG, MONO),
    ("Escrow balance after every scenario: 0", GREEN, MONO_BIG),
    ("The contract never keeps funds.", FG, MONO_BIG),
]
for _ in range(90):
    p = OUT_DIR / f"f{n:04d}.png"
    frame(end, p)
    frames.append(p)
    n += 1

out = ROOT / "build" / "demo-video.mp4"
subprocess.run(
    ["ffmpeg", "-y", "-framerate", "30", "-i", str(OUT_DIR / "f%04d.png"),
     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(out)],
    check=True, capture_output=True, text=True,
)
print(f"wrote {out} ({n} frames, {n/30:.0f}s)")
