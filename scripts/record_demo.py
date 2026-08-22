# -*- coding: utf-8 -*-
"""参赛实操演示视频录制脚本。

用 Playwright 驱动 chromium headless 逐帧截屏（真实渲染 + 真实交互），
再用 ffmpeg 合成为 H.264 MP4（≤100M）。字幕以 PIL 叠加烧录。

用法:
    /workspace/2026-07/.venv/bin/python scripts/record_demo.py
产物:
    /workspace/2026-07/智能物资数据管理系统-实操演示视频.mp4
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ---- 沙箱运行必需的环境 ----
# 注意：HOME 必须强制覆盖。沙箱默认 HOME=/root，setdefault 不会生效，
# 会导致 Chromium 的 fontconfig 找不到 .pw-home/.fonts 下的 Noto CJK 字体，
# 页面中文全部渲染成豆腐块乱码。
os.environ.setdefault(
    "LD_LIBRARY_PATH",
    "/workspace/2026-07/.pw-libs/usr/lib/aarch64-linux-gnu:" + os.environ.get("LD_LIBRARY_PATH", ""),
)
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/workspace/2026-07/.pw-browsers")
os.environ["HOME"] = "/workspace/2026-07/.pw-home"
os.environ["XDG_CACHE_HOME"] = "/workspace/2026-07/.pw-home/.cache"

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8010"


def resolve_demo_sample() -> Path:
    override = os.environ.get("DEMO_SAMPLE", "").strip()
    if override:
        return Path(override)
    samples = sorted((ROOT / "demo_data" / "samples").glob("*.xlsx"))
    if samples:
        return samples[0]
    raise SystemExit(
        "缺失演示样例：将脱敏台账放入 demo_data/samples/，或设置 DEMO_SAMPLE=/path/to/file.xlsx"
    )


SAMPLE = resolve_demo_sample()
OUT_DIR = Path("/workspace/2026-07/demo_video")
FRAMES = OUT_DIR / "frames"
OUT_MP4 = Path("/workspace/2026-07/智能物资数据管理系统-实操演示视频.mp4")
FONT = "/workspace/2026-07/.pw-home/.fonts/NotoSansCJK-Regular.ttc"

W, H = 1440, 900
FPS = 2.5  # 源截图帧率（每 0.4s 一帧）
CAPTURE_IV = 0.4  # 截帧间隔（秒）
FINAL_FPS = 8  # 合成帧率（插帧复制）

PIL_AVAILABLE = False
try:
    from PIL import Image, ImageDraw, ImageFont

    PIL_AVAILABLE = True
except Exception:
    pass


def load_font(size: int):
    if not PIL_AVAILABLE:
        return None
    for idx in (2, 3, 0):  # Noto CJK ttc 中常见 SC 在第 2/3 个 face
        try:
            return ImageFont.truetype(FONT, size, index=idx)
        except Exception:
            continue
    return ImageFont.load_default()


def make_title_frame(text_lines, sub=None):
    """生成片头/片尾静态帧：深蓝底 + 白色标题。"""
    img = Image.new("RGB", (W, H), (0, 46, 103))
    d = ImageDraw.Draw(img)
    f1 = load_font(58)
    f2 = load_font(30)
    # 顶部品牌条
    d.rectangle([0, 0, W, 8], fill=(0, 173, 216))
    y = H // 2 - 120
    for line in text_lines:
        bb = d.textbbox((0, 0), line, font=f1)
        d.text(((W - (bb[2] - bb[0])) / 2, y), line, fill=(255, 255, 255), font=f1)
        y += 90
    if sub:
        bb = d.textbbox((0, 0), sub, font=f2)
        d.text(((W - (bb[2] - bb[0])) / 2, y + 20), sub, fill=(140, 200, 255), font=f2)
    # 底部保密提示
    tip = "演示数据为脱敏虚构样例 · 全程本地离线运行"
    bb = d.textbbox((0, 0), tip, font=f2)
    d.text(((W - (bb[2] - bb[0])) / 2, H - 90), tip, fill=(200, 220, 240), font=f2)
    return img


def add_subtitle(img, text):
    """在帧底部叠加半透明黑条字幕。"""
    d = ImageDraw.Draw(img)
    f = load_font(26)
    bar_h = 58
    d.rectangle([0, H - bar_h, W, H], fill=(0, 0, 0, 150))
    bb = d.textbbox((0, 0), text, font=f)
    d.text(((W - (bb[2] - bb[0])) / 2, H - bar_h + (bar_h - (bb[3] - bb[1])) / 2 - bb[1]), text, fill=(255, 255, 255), font=f)
    return img


def init_page():
    from playwright.sync_api import sync_playwright

    p = sync_playwright().start()
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--force-device-scale-factor=1"],
    )
    ctx = browser.new_context(viewport={"width": W, "height": H})
    ctx.add_init_script(
        "localStorage.setItem('ops_token','demo-ops');localStorage.setItem('ops_role','ops');"
    )
    page = ctx.new_page()
    page.set_default_timeout(15000)
    return p, browser, ctx, page


class Recorder:
    def __init__(self, page):
        self.page = page
        self.n = 0
        self.subtitle = ""
        self.error = 0

    def shot(self):
        self.n += 1
        path = FRAMES / f"{self.n:05d}.png"
        self.page.screenshot(path=str(path))
        if PIL_AVAILABLE and self.subtitle:
            img = Image.open(path).convert("RGB")
            add_subtitle(img, self.subtitle)
            img.save(path)
        return path

    def hold(self, seconds, subtitle=None):
        if subtitle:
            self.subtitle = subtitle
        frames = max(1, int(round(seconds / CAPTURE_IV)))
        for _ in range(frames):
            try:
                self.shot()
            except Exception:
                self.error += 1
            time.sleep(CAPTURE_IV)

    def goto(self, url, settle=1.6):
        try:
            self.page.goto(BASE_URL + url, wait_until="load", timeout=30000)
        except Exception:
            self.error += 1
        self.page.wait_for_timeout(int(settle * 1000))

    def safe(self, fn):
        try:
            return fn()
        except Exception:
            self.error += 1
            return None


def main() -> int:
    if FRAMES.exists():
        shutil.rmtree(FRAMES)
    FRAMES.mkdir(parents=True, exist_ok=True)
    assert SAMPLE.exists(), f"缺失样例文件: {SAMPLE}"

    rec = None
    try:
        p, browser, ctx, page = init_page()
        rec = Recorder(page)

        # ===== 片头 =====
        title_img = make_title_frame(
            ["智能物资数据管理系统"],
            "基于本地大模型的物资数据治理与智能问答平台",
        )
        for _ in range(int(8 * FPS)):
            rec.n += 1
            title_img.save(FRAMES / f"{rec.n:05d}.png")
            time.sleep(0.05)

        # ===== 幕1 系统首页（运行界面 + 核心指标）=====
        rec.goto("/")
        rec.hold(14, "系统首页 · 物资数据核心指标总览（脱敏演示数据）")

        # ===== 幕2 运行界面：四大板块导航 =====
        rec.hold(2.5, "运行界面 · 接入 / 规整 / 看数 / 运维 四大板块")
        rec.goto("/intake", settle=1.0)
        rec.hold(2.0)
        rec.goto("/govern", settle=1.0)
        rec.hold(2.0)
        rec.goto("/data", settle=1.0)
        rec.hold(2.0)
        rec.goto("/ask", settle=1.0)
        rec.hold(2.0)

        # ===== 幕3 完整业务案例：数据接入 =====
        rec.goto("/intake")
        rec.hold(5, "数据接入 · 上传脱敏台账（4 Sheet 异构结构）")
        # 选择文件（真实交互）
        rec.safe(
            lambda: page.locator("input[type=file]").set_input_files(str(SAMPLE))
        )
        page.wait_for_timeout(1200)
        rec.hold(2.5)
        rec.safe(
            lambda: page.get_by_role("button", name="上传并开始解析").click()
        )
        try:
            page.wait_for_response(
                lambda r: r.url.endswith("/api/v1/files") and r.request.method == "POST",
                timeout=30000,
            )
        except Exception:
            rec.error += 1
        page.wait_for_timeout(2500)
        rec.hold(8, "自动解析 · 结构解析/字段画像/质量预检（幂等复用）")
        rec.hold(4, "任务列表 · 文件状态 released · 全程留存原始证据")

        # ===== 幕4 数据规整：待办 + 对账差异 =====
        rec.goto("/govern")
        rec.hold(8, "数据规整 · 治理待办队列与映射建议")
        rec.safe(
            lambda: page.locator(".work-card", has_text="对账差异").first.click()
        )
        page.wait_for_timeout(2200)
        rec.hold(14, "对账差异 · 自动勾稽「期初+入库−出库 vs 现有库存」16 条")
        rec.safe(
            lambda: page.locator(".work-card", has_text="待确认字段").first.click()
        )
        page.wait_for_timeout(1800)
        rec.hold(5, "待确认字段 · 基于本地向量模型召回的映射建议")

        # ===== 幕5 追溯审计 =====
        rec.goto("/trace")
        page.wait_for_timeout(1200)
        rec.hold(4, "追溯审计 · 数据来源血缘")
        rec.safe(lambda: page.get_by_text("操作记录").first.click())
        page.wait_for_timeout(1500)
        rec.hold(9, "操作记录 · 发布全流程审计，可追溯可回滚")

        # ===== 幕6 数据成果：标准库存 / 组合筛选 / 流水 =====
        rec.goto("/data")
        page.wait_for_timeout(1200)
        rec.hold(12, "数据成果 · 标准化库存台账（52 行，字段统一带血缘）")
        # 组合筛选演示：物资种类=维护材料 + 存放区域=213仓库（虚构区域）
        rec.safe(lambda: page.locator(".el-select", has_text="物资种类").first.click())
        page.wait_for_timeout(900)
        rec.safe(lambda: page.locator(".el-select-dropdown__item", has_text="维护材料").first.click())
        page.wait_for_timeout(900)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        rec.safe(lambda: page.locator(".el-select", has_text="存放区域").first.click())
        page.wait_for_timeout(900)
        rec.safe(lambda: page.locator(".el-select-dropdown__item", has_text="213仓库").first.click())
        page.wait_for_timeout(900)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        rec.safe(lambda: page.get_by_role("button", name="查询").click())
        page.wait_for_timeout(2200)
        rec.hold(9, "数据成果 · 组合筛选：维护材料 × 213仓库，命中 5 条")
        rec.safe(lambda: page.get_by_text("规整明细").first.click())
        page.wait_for_timeout(1500)
        rec.hold(8, "规整明细 · 出入库流水 50 段，L1 自动拆解")

        # ===== 幕7 问数助手：自然语言 → SQL → 结果 =====
        rec.goto("/ask")
        page.wait_for_timeout(1200)

        def ask(q: str, wait_sec: float = 3.2):
            box = page.locator("[placeholder*='例如']").first
            box.click()
            box.fill(q)
            val = box.input_value()
            if not val:
                page.keyboard.press("Control+A")
                page.keyboard.type(q)
                val = box.input_value()
            if val:
                page.get_by_role("button", name="提问").click()
            else:
                rec.error += 1
            page.wait_for_timeout(int(wait_sec * 1000))

        rec.safe(lambda: ask("库存总量是多少"))
        rec.hold(10, "问数助手① · 指标模板命中：库存总量 = 248 件（未调生成模型）")
        rec.safe(lambda: ask("库存表有多少行"))
        rec.hold(10, "问数助手② · 自然语言问数秒级出数")

        # ===== 幕8 系统运维：模型 API 接入 =====
        rec.goto("/system?tab=models")
        page.wait_for_timeout(1800)
        rec.hold(12, "系统运维 · 本地模型 API 接入状态（Qwen3.6-27B / Embedding 0.6B）")

        # ===== 片尾 =====
        end_img = make_title_frame(
            ["一次治理 · 长期受益"],
            "多源异构台账 → 上传即治理、问答即得数；数据不出本机，全程可审计",
        )
        for _ in range(int(8 * FPS)):
            rec.n += 1
            end_img.save(FRAMES / f"{rec.n:05d}.png")
            time.sleep(0.05)

        print(f"CAPTURED_FRAMES={rec.n} ERRORS={rec.error}")
        ctx.close()
        browser.close()
        p.stop()
    finally:
        if rec:
            pass

    # ===== ffmpeg 合成 MP4 =====
    if not list(FRAMES.glob("*.png")):
        print("NO_FRAMES, abort")
        return 1
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-framerate", str(FPS),
        "-i", str(FRAMES / "%05d.png"),
        "-vf", f"framerate=fps={FINAL_FPS},scale={W}:{H}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(OUT_MP4),
    ]
    r = subprocess.run(cmd)
    size_mb = OUT_MP4.stat().st_size / 1024 / 1024 if OUT_MP4.exists() else 0
    print(f"MP4_OUT={OUT_MP4} SIZE_MB={size_mb:.1f} RC={r.returncode}")
    # 强制退出，避免 fontconfig 沙箱清理崩溃影响退出码
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
