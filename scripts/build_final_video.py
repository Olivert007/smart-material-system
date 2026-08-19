# -*- coding: utf-8 -*-
"""为实操演示视频生成配音音轨 + 详细字幕，并合成最终 MP4。

流程：
1. 按幕时间轴用 edge-tts（微软 TTS，中文女声 Xiaoxiao）逐段生成配音
2. 每段音频变速对齐到对应画面时段，拼接为完整音轨
3. 生成 SRT 字幕（供外部使用）与 ASS 字幕（含样式，用于烧录）
4. ffmpeg 合成：原视频 + 音轨 + 烧录字幕

用法:
    /usr/bin/python3 scripts/build_final_video.py
产物:
    /workspace/2026-07/智能物资数据管理系统-实操演示视频-配音版.mp4
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

BASE = Path("/workspace/2026-07")
SRC_VIDEO = BASE / "智能物资数据管理系统-实操演示视频.mp4"
OUT_VIDEO = BASE / "智能物资数据管理系统-实操演示视频-配音版.mp4"
AUD_DIR = BASE / "demo_video" / "narration"
SUB_SRT = BASE / "demo_video" / "subtitle.srt"
FONT_HOME = Path("/workspace/2026-07/.pw-home")

VOICE = "zh-CN-XiaoxiaoNeural"
VIDEO_DUR = 160.0  # 视频总时长（秒）

# (id, 起始s, 结束s, 字幕, 配音文案)
SCENES = [
    ("intro", 0.0, 8.0,
     "作品：《智能物资数据管理系统》——基于本地大模型的物资数据治理与智能问答平台",
     "大家好，我演示的作品是“智能物资数据管理系统”——基于本地大模型的物资数据治理与智能问答平台。"),
    ("home", 8.0, 21.6,
     "系统首页 · 物资库核心指标总览",
     "这是系统首页，集中展示物资库核心指标：库存总量、库存金额、需求总量、资产数量等，所有指标口径统一、带字典说明。"),
    ("nav", 21.6, 32.0,
     "四大板块 · 接入 / 规整 / 看数 / 运维",
     "系统按业务旅程组织为四大板块：数据接入、数据规整、数据成果与问数助手、系统运维。"),
    ("intake", 32.4, 51.2,
     "数据接入 · 上传脱敏台账并自动解析",
     "下面演示一个完整案例。上传一份四 Sheet 的物资台账，包含异构列结构、空字段与口径不一致的脏数据；系统自动完成结构解析、字段画像与质量预检，全程留存原始证据。"),
    ("govern", 51.6, 78.0,
     "数据规整 · 映射建议与勾稽差异 16 条",
     "治理中心给出列映射建议，基于本地向量模型召回，人工一键确认；系统自动勾稽“期初加入库减出库，与现有库存”的差异，共发现十六条口径不一致记录，把人工对账的隐患提前暴露。"),
    ("trace", 78.4, 90.8,
     "追溯审计 · 发布记录可追溯可回滚",
     "确认后经唯一写入入口防重发布，写入标准库；整个过程写入审计时间线，可追溯、可回滚。"),
    ("data", 91.2, 119.6,
     "数据成果 · 标准库存 52 行 / 组合筛选 5 条 / 流水 50 段",
     "发布的成果落为标准星型模型：事实库存表五十二行、出入库流水五十段，字段统一、带来源血缘。台账还支持组合筛选，选物资种类“维护材料”、存放区域“213仓库”，秒级命中五条记录。"),
    ("ask", 120.0, 139.6,
     "问数助手 · 自然语言问数秒级出数",
     "现在用自然语言查数：问库存总量是多少，系统命中指标口径模板，直接返回二百四十八件；再问库存表有多少行，同样秒级出数。查询只读、防注入。"),
    ("models", 140.0, 151.6,
     "系统运维 · 本地模型 API 接入，数据不出本机",
     "系统的 AI 能力全部来自本地部署的模型，走内网 OpenAI 兼容 API；数据不出本机，从根本上满足保密要求。"),
    ("outro", 152.0, 159.6,
     "一次治理 · 长期受益",
     "这套系统把多源异构台账的治理周期，从人工数周压缩到上传即得。谢谢观看。"),
]


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print(f"[warn] rc={r.returncode}: {' '.join(cmd)}\n{r.stderr[-500:]}")
    return r


def synth(scene_id: str, text: str) -> Path:
    """edge-tts 生成 mp3，返回文件路径。"""
    out = AUD_DIR / f"{scene_id}.mp3"
    if out.exists():
        return out
    r = run(
        [sys.executable, "-m", "edge_tts", "--voice", VOICE, "--text", text, "--write-media", str(out)],
        env={**os.environ},
    )
    if not out.exists():
        raise RuntimeError(f"TTS failed for {scene_id}")
    return out


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


def fmt_ts(sec: float) -> str:
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def build_srt() -> Path:
    """生成 SRT（供外部工具/字幕文件使用）。"""
    lines = []
    for i, (sid, s, e, sub, _txt) in enumerate(SCENES, 1):
        lines.append(str(i))
        lines.append(f"{fmt_ts(s)} --> {fmt_ts(e)}")
        lines.append(sub)
        lines.append("")
    SUB_SRT.write_text("\n".join(lines), encoding="utf-8")
    return SUB_SRT


def ass_ts(sec: float) -> str:
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_ass() -> Path:
    """生成 ASS 字幕（底部半透明黑底框 + 白字），用于 ffmpeg 烧录。

    重要：不要声明 PlayResX/PlayResY——实测本环境 ffmpeg subtitles 滤镜 + libass
    0.15 在声明 PlayRes 后不渲染任何字幕（rc=0 但画面无变化）。去掉 PlayRes 后
    libass 按默认脚本分辨率 384x288 渲染，对 1440x900 视频缩放约 3.125 倍，
    因此 Fontsize/MarginV 按 1/3.125 取值即可得到期望的实际像素效果
    （Fontsize 11 -> 约 34px 字；MarginV 22 -> 距底部约 69px）。
    """
    ass = SUB_SRT.with_suffix(".ass")
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Noto Sans CJK SC,11,&H00FFFFFF,&H000000FF,&H00000000,"
        "&H80000000,0,0,0,0,100,100,0,0,3,1,0,2,20,20,22,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = [header]
    for sid, s, e, sub, _txt in SCENES:
        lines.append(f"Dialogue: 0,{ass_ts(s)},{ass_ts(e)},Default,,0,0,0,,{sub}")
    ass.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ass


def main() -> int:
    assert SRC_VIDEO.exists(), f"缺少原视频: {SRC_VIDEO}"
    AUD_DIR.mkdir(parents=True, exist_ok=True)

    # 1) TTS 逐段生成
    segs = []
    for sid, s, e, _sub, txt in SCENES:
        seg = synth(sid, txt)
        segs.append((sid, s, e, seg))
        print(f"synth {sid}: {seg_duration(seg):.1f}s", flush=True)

    # 2) 构建 filter_complex：每段 adelay 对齐，超长则 atempo 压缩到幕内
    #    输入 0 为原视频（无音轨），配音音频从输入 1 开始
    filt = []
    inputs = []
    idx = 0
    for sid, s, e, seg in segs:
        d = seg_duration(seg)
        slot = max(0.1, e - s - 0.6)  # 幕内可用时长（留 0.6s 余量）
        inputs += ["-i", str(seg)]
        ain = idx + 1  # 音频输入索引
        if d > slot:
            rate = d / slot
            if rate > 1.35:
                rate = 1.35  # 最多加速 1.35x，超出部分让字幕提前结束
            filt.append(
                f"[{ain}:a]atempo={rate:.4f},adelay={int(s * 1000)}|{int(s * 1000)}[a{idx}]"
            )
        else:
            filt.append(f"[{ain}:a]adelay={int(s * 1000)}|{int(s * 1000)}[a{idx}]")
        idx += 1
    mix = "".join(f"[a{i}]" for i in range(idx))
    filt.append(f"{mix}amix=inputs={idx}:normalize=0:dropout_transition=0[out]")

    # 3) 合成视频
    srt = build_srt()
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(SRC_VIDEO),
        *inputs,
        "-filter_complex", ";".join(filt),
        "-map", "0:v", "-map", "[out]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k",
        "-t", str(VIDEO_DUR),
        "-metadata:s:a", "language=chi",
        str(OUT_VIDEO),
    ]
    r = run(cmd)
    print(f"AUDIO_MIX_RC={r.returncode}")

    # 4) 烧录字幕（基于配音版，无画面重编码）
    out_final = OUT_VIDEO
    out_burned = OUT_VIDEO.with_name(OUT_VIDEO.stem + "-字幕.mp4")
    # HOME 指向字体目录；样式已内嵌在 ASS 中（底部半透明黑底框 + 白字）
    env = {**os.environ, "HOME": str(FONT_HOME)}
    cmd2 = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(OUT_VIDEO),
        "-vf", f"subtitles={build_ass()}",
        "-c:a", "copy",
        "-c:v", "libx264", "-preset", "medium", "-crf", "21",
        "-pix_fmt", "yuv420p",
        str(out_burned),
    ]
    r2 = run(cmd2, env=env)
    print(f"BURN_RC={r2.returncode} OUT={out_burned}")

    # 若烧录失败，退回未烧录版
    if not out_burned.exists():
        print("字幕烧录失败，保留配音版（无字幕）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
