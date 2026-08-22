#!/usr/bin/env python3
"""合成最终两版视频：
1. 纯视频版（无配音）
2. 配音版（无字幕，配音按幕时间轴对齐）

用法: /usr/bin/python3 build_final_video_v2.py <源webm或mp4>
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BASE = Path("/workspace/2026-07")
SRC = Path(sys.argv[1])
AUD_DIR = BASE / "demo_video" / "narration_v4"
OUT_DIR = BASE / "demo_video"
VIDEO_TOTAL = 328.0  # 与录制脚本 v4 时间轴一致

# (id, 起始s, 结束s) —— 14 镜头（v4 精简版）
SCENES = [
    ("cover", 0.0, 22.0),
    ("home", 22.0, 42.0),
    ("intake", 42.0, 70.0),
    ("govern_hub", 70.0, 85.0),
    ("govern_flow", 85.0, 128.0),
    ("govern_reconcile", 128.0, 156.0),
    ("govern_release", 156.0, 172.0),
    ("data_materials", 172.0, 198.0),
    ("data_trend", 198.0, 224.0),
    ("ask_metric", 224.0, 244.0),
    ("ask_complex", 244.0, 268.0),
    ("trace", 268.0, 288.0),
    ("models", 288.0, 310.0),
    ("outro", 310.0, 328.0),
]

OUT_PLAIN = OUT_DIR / "智能物资数据管理系统-演示视频-纯视频版.mp4"
OUT_VOICE = OUT_DIR / "智能物资数据管理系统-演示视频-配音版.mp4"


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print(f"[warn] rc={r.returncode}: {' '.join(cmd)}\n{r.stderr[-500:]}")
    return r


def seg_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def main() -> int:
    assert SRC.exists(), f"缺少源视频: {SRC}"

    # 1) 纯视频版：webm/mp4 → h264 mp4（无音轨，16:9）
    r = run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(SRC),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-an",
        str(OUT_PLAIN),
    ])
    print(f"PLAIN_RC={r.returncode} OUT={OUT_PLAIN} ({seg_duration(OUT_PLAIN):.1f}s)")
    if not OUT_PLAIN.exists():
        return 1

    # 2) 配音版：按幕时间轴对齐配音并合成
    filt = []
    inputs = ["-i", str(OUT_PLAIN)]
    idx = 0
    for sid, s, e in SCENES:
        seg = AUD_DIR / f"{sid}.mp3"
        if not seg.exists():
            print(f"  [warn] 缺少配音: {seg}")
            continue
        d = seg_duration(seg)
        slot = max(0.1, e - s - 0.8)  # 幕内可用时长（留 0.8s 余量）
        inputs += ["-i", str(seg)]
        ain = idx + 1
        if d > slot:
            rate = d / slot
            if rate > 1.35:
                rate = 1.35
            filt.append(
                f"[{ain}:a]atempo={rate:.4f},adelay={int(s * 1000)}|{int(s * 1000)}[a{idx}]"
            )
            print(f"  {sid}: {d:.1f}s -> slot {slot:.1f}s (atempo {rate:.2f})")
        else:
            filt.append(f"[{ain}:a]adelay={int(s * 1000)}|{int(s * 1000)}[a{idx}]")
            print(f"  {sid}: {d:.1f}s -> slot {slot:.1f}s (原速)")
        idx += 1
    mix = "".join(f"[a{i}]" for i in range(idx))
    filt.append(f"{mix}amix=inputs={idx}:normalize=0:dropout_transition=0[out]")

    r2 = run([
        "ffmpeg", "-y", "-loglevel", "error",
        *inputs,
        "-filter_complex", ";".join(filt),
        "-map", "0:v", "-map", "[out]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "160k",
        "-t", str(VIDEO_TOTAL),
        "-metadata:s:a", "language=chi",
        str(OUT_VOICE),
    ])
    print(f"VOICE_RC={r2.returncode} OUT={OUT_VOICE} ({seg_duration(OUT_VOICE):.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
