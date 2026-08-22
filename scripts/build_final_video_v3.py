#!/usr/bin/env python3
"""V5 合成：读取录制时间轴 JSON，配音精确对齐镜头（无静默空洞）。

用法: /usr/bin/python3 build_final_video_v3.py <源mp4> [timeline.json]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BASE = Path("/workspace/2026-07")
SRC = Path(sys.argv[1])
TIMELINE_JSON = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/tmp/shot_timeline.json")
AUD_DIR = BASE / "demo_video" / "narration_v4"
OUT_DIR = BASE / "demo_video"

OUT_PLAIN = OUT_DIR / "智能物资数据管理系统-演示视频-纯视频版.mp4"
OUT_VOICE = OUT_DIR / "智能物资数据管理系统-演示视频-配音版.mp4"

ORDER = [
    "cover", "home", "intake", "govern_hub", "govern_flow", "govern_reconcile",
    "govern_release", "data_materials", "data_trend", "ask_metric", "ask_complex",
    "trace", "models", "outro",
]


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print(f"[warn] rc={r.returncode}: {' '.join(cmd)}\n{r.stderr[-400:]}")
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
    timeline: dict[str, float] = json.loads(TIMELINE_JSON.read_text(encoding="utf-8"))
    total = max(timeline.values()) + 20.0  # 最后一个镜头结束后留 20s（收尾画面）
    for name in ORDER:
        assert name in timeline, f"timeline 缺少镜头 {name}"
    print(f"timeline: {timeline}", flush=True)

    # 1) 纯视频版
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

    # 2) 配音版：每段 adelay 到对应镜头 start
    filt = []
    inputs = ["-i", str(OUT_PLAIN)]
    idx = 0
    for name in ORDER:
        seg = AUD_DIR / f"{name}.mp3"
        if not seg.exists():
            print(f"  [warn] 缺少配音: {seg}")
            continue
        s = timeline[name]
        d = seg_duration(seg)
        inputs += ["-i", str(seg)]
        ain = idx + 1
        filt.append(f"[{ain}:a]adelay={int(s * 1000)}|{int(s * 1000)}[a{idx}]")
        print(f"  {name}: start={s:.1f}s dur={d:.1f}s (原速)")
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
        "-t", str(total),
        "-metadata:s:a", "language=chi",
        str(OUT_VOICE),
    ])
    print(f"VOICE_RC={r2.returncode} OUT={OUT_VOICE} ({seg_duration(OUT_VOICE):.1f}s) TOTAL={total:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
