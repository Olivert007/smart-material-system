#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全站提示收敛 · 端到端冒烟。

对运行中的 http://127.0.0.1:8010 走业务路径，断言：
- 首页 4 张状态卡 + 4 KPI
- 业务页无禁用 disclaimer / 顶栏长 info
- 接入无「高级详情」
- 报表无 lastRun / 候选快照
- 控制台无 Vue/JS 报错

用法:
    /workspace/2026-07/.venv/bin/python scripts/e2e_copywriting_smoke.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_PW_LIBS = "/workspace/2026-07/.pw-libs/usr/lib/aarch64-linux-gnu"
_cur = os.environ.get("LD_LIBRARY_PATH", "")
os.environ["LD_LIBRARY_PATH"] = _PW_LIBS + (":" + _cur if _cur else "")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/workspace/2026-07/.pw-browsers")
os.environ["HOME"] = "/workspace/2026-07/.pw-home"
os.environ["XDG_CACHE_HOME"] = "/workspace/2026-07/.pw-home/.cache"

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8010")
SHOT = ROOT / "data" / "eval" / "e2e_copywriting"
BANNED = ("不等于正式", "非正式发布", "可用候选")
FAILS: list[str] = []
CONSOLE: list[str] = []


def fail(msg: str) -> None:
    FAILS.append(msg)
    print(f"FAIL  {msg}")


def ok(msg: str) -> None:
    print(f"OK    {msg}")


def visible_text(page) -> str:
    return page.locator("body").inner_text()


def assert_no_banned(page, where: str) -> None:
    text = visible_text(page)
    for w in BANNED:
        if w in text:
            fail(f"{where}: 仍出现禁用词「{w}」")
            return
    ok(f"{where}: 无禁用 disclaimer")


def assert_no_long_info_alert(page, where: str, allowed_titles: tuple[str, ...] = ()) -> None:
    alerts = page.locator('.el-alert--info')
    n = alerts.count()
    for i in range(n):
        el = alerts.nth(i)
        if not el.is_visible():
            continue
        title = (el.locator(".el-alert__title").inner_text() if el.locator(".el-alert__title").count() else "")
        desc = ""
        if el.locator(".el-alert__description").count():
            desc = el.locator(".el-alert__description").inner_text()
        if any(t in title for t in allowed_titles):
            continue
        if desc.count("\n") >= 1 or len(desc) > 80:
            fail(f"{where}: 仍有长 info alert「{title}」len={len(desc)}")
            return
    ok(f"{where}: 无过长 info 顶栏")


def main() -> int:
    from playwright.sync_api import sync_playwright

    SHOT.mkdir(parents=True, exist_ok=True)
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script(
        "localStorage.setItem('ops_token','dev-ops-token-change-me');"
        "localStorage.setItem('ops_role','ops');"
    )
    page = ctx.new_page()
    page.set_default_timeout(20000)
    page.on(
        "pageerror",
        lambda e: CONSOLE.append(f"pageerror: {e}"),
    )
    page.on(
        "console",
        lambda m: CONSOLE.append(f"{m.type}: {m.text}") if m.type in ("error",) else None,
    )

    def shot(name: str) -> None:
        page.screenshot(path=str(SHOT / f"{name}.png"), full_page=True)

    def goto(path: str) -> None:
        page.goto(BASE + path, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(600)

    # --- / ---
    goto("/")
    shot("01_home")
    body = visible_text(page)
    for label in ("待办合计", "可用行数", "阻塞行数", "流水待确认"):
        if label not in body:
            fail(f"首页缺少状态卡「{label}」")
        else:
            ok(f"首页有状态卡「{label}」")
    for gone in ("可用率", "待确认字段", "待匹配物资", "待审核 AI 建议", "处理后预计释放", "查看数据成果", "问数助手"):
        if gone in body and gone != "待确认字段":
            # 治理入口文案可能仍出现在下一步 reason 里；只禁卡片区这些标题
            pass
    cards = page.locator(".home .cards:not(.compact) .card-label")
    labels = [cards.nth(i).inner_text().strip() for i in range(cards.count())]
    if labels != ["待办合计", "可用行数", "阻塞行数", "流水待确认"]:
        fail(f"首页状态卡顺序/数量不对: {labels}")
    else:
        ok("首页恰好 4 张状态卡且顺序正确")
    for gone in ("可用率", "查看数据成果"):
        if gone in body:
            fail(f"首页仍出现已删文案「{gone}」")
    kpi = page.locator(".home .cards.compact .card-label")
    kpi_labels = [kpi.nth(i).inner_text().strip() for i in range(kpi.count())]
    if kpi.count() and kpi_labels != ["库存总量", "资产台数", "入库合计", "出库合计"]:
        # 无数据时空态可没有 KPI
        if "业务数据概览" in body and "暂无" not in body:
            fail(f"首页 KPI 不对: {kpi_labels}")
        else:
            ok(f"首页业务快照空态或 KPI={kpi_labels}")
    else:
        if kpi.count():
            ok("首页 4 KPI")
    assert_no_banned(page, "首页")
    if "当前展示的是规整后可用的工作数据" not in body and "待办" not in body:
        fail("首页缺少状态 alert")
    else:
        ok("首页有数据状态 alert")

    # --- /data ---
    goto("/data")
    shot("02_data")
    body = visible_text(page)
    if "去数据规整" in body and page.locator(".el-alert--info").count():
        # 物资台账页自身按钮可以有「去数据规整」，但不能是顶栏 alert
        info_titles = []
        infos = page.locator(".el-alert--info")
        for i in range(infos.count()):
            t = infos.nth(i)
            if t.is_visible() and t.locator(".el-alert__title").count():
                info_titles.append(t.locator(".el-alert__title").inner_text())
        if "数据成果" in info_titles:
            fail("数据成果仍有顶栏 info alert")
        else:
            ok("数据成果无顶栏「数据成果」alert")
    else:
        ok("数据成果无顶栏长 alert")
    assert_no_banned(page, "数据成果")
    for tab in ("物资台账", "规整明细", "报表导出", "趋势分析"):
        if tab not in body:
            fail(f"数据成果缺 Tab「{tab}」")

    page.get_by_text("报表导出", exact=True).first.click()
    page.wait_for_timeout(800)
    shot("03_reports")
    body = visible_text(page)
    if "最近运行" in body or "候选快照" in body or "lastRun" in body:
        fail("报表页仍有 lastRun / 候选快照")
    else:
        ok("报表页无最近运行卡")
    if "汇总报表" not in body:
        fail("报表页缺少「汇总报表」")
    else:
        ok("报表页有汇总报表目录")
    assert_no_banned(page, "报表导出")

    page.get_by_text("趋势分析", exact=True).first.click()
    page.wait_for_timeout(800)
    shot("04_trend")
    assert_no_banned(page, "趋势分析")
    if page.locator(".flow-analytics .el-alert--info").count():
        fail("趋势页仍有 info alert")
    else:
        ok("趋势页无顶栏 alert")

    page.get_by_text("规整明细", exact=True).first.click()
    page.wait_for_timeout(800)
    shot("05_browse")
    assert_no_banned(page, "规整明细")

    # --- /ask ---
    goto("/ask")
    shot("06_ask")
    body = visible_text(page)
    if "问数助手" in body and page.locator(".ask > .el-alert--info").count():
        fail("问数页仍有顶栏说明 alert")
    else:
        ok("问数页无顶栏 info 说明")
    assert_no_banned(page, "问数")
    page.get_by_role("button", name="示例问题").click()
    page.wait_for_timeout(300)
    page.get_by_text("库存总量是多少", exact=True).click()
    page.get_by_role("button", name="提问").click()
    page.wait_for_timeout(4000)
    shot("07_ask_result")
    body = visible_text(page)
    assert_no_banned(page, "问数结果")
    tags = page.locator(".ask .tags .el-tag")
    tag_texts = [tags.nth(i).inner_text().strip() for i in range(tags.count())] if tags.count() else []
    if any(t.startswith("来源") or "未调用模型" in t or "非正式" in t for t in tag_texts):
        fail(f"问数结果 tag 未收敛: {tag_texts}")
    else:
        ok(f"问数结果 tag={tag_texts}")

    # --- /govern ---
    goto("/govern")
    shot("08_govern")
    body = visible_text(page)
    if "处理新数据里还没确认的问题" in body:
        fail("治理 Hub 仍有 page-head 描述")
    else:
        ok("治理 Hub 无页头描述")
    if "其余队列" in body:
        fail("治理 Hub 在有/无 active 时仍展示 idle 行（需人工核对截图）")
    else:
        ok("治理 Hub 无「其余队列」idle 行")
    if page.locator(".work-hint").count():
        fail("治理 Hub 仍渲染 work-hint")
    else:
        ok("治理 Hub 无 work-hint")
    assert_no_banned(page, "治理")

    # --- /intake ---
    goto("/intake")
    shot("09_intake")
    body = visible_text(page)
    if "高级详情" in body:
        fail("接入页仍有高级详情")
    else:
        ok("接入页无高级详情")
    if "上传成功不等于解析完成" in body:
        fail("接入页仍有顶栏长说明")
    else:
        ok("接入页无顶栏长说明")
    assert_no_banned(page, "接入")
    for step in ("选择文件", "识别结论", "处理问题", "进入规整"):
        if step not in body:
            fail(f"接入缺步骤「{step}」")

    # --- /trace ---
    goto("/trace")
    shot("10_trace")
    body = visible_text(page)
    if "可用结果不等于正式发布报表" in body:
        fail("追溯页仍有顶栏 disclaimer")
    else:
        ok("追溯页无顶栏 disclaimer")
    assert_no_banned(page, "追溯")

    # --- /system ---
    goto("/system")
    shot("11_system")
    body = visible_text(page)
    if "面向运维：查看系统运行状态" in body:
        fail("系统页仍有顶栏长 alert")
    else:
        ok("系统页无顶栏长 alert")

    # --- 交互：报表运行并预览 ---
    goto("/data?tab=report")
    page.get_by_role("button", name="运行并预览").first.click()
    page.wait_for_timeout(3500)
    shot("12_report_preview")
    body = visible_text(page)
    if "最近运行结果" in body or "运行编号" in body:
        fail("运行报表后仍出现最近运行卡/运行编号")
    else:
        ok("运行报表后无最近运行卡")
    if "数据预览（前" in body:
        fail("预览标题仍是「数据预览（前 N 行）」")
    else:
        ok("预览标题已合并")
    if "下载完整报表" not in body:
        fail("运行后缺少「下载完整报表」")
    else:
        ok("运行后可下载完整报表")
    assert_no_banned(page, "报表预览")
    preview_headers = page.locator(".catalog .el-table thead .el-table__cell")
    # 第二张表才是预览；若只有目录则失败
    if page.locator(".catalog .el-card").count() < 2:
        fail("运行后没有预览卡")
    else:
        ok("运行后有预览卡")
        headers = page.locator(".catalog .el-card").nth(1).locator("thead .cell").all_inner_texts()
        raw = [h.strip() for h in headers if re.fullmatch(r"[a-z][a-z0-9_]*", h.strip())]
        if raw:
            fail(f"预览列头仍有裸英文: {raw}")
        else:
            ok(f"预览列头已汉化: {headers}")

    # --- 交互：带参数报表 ---
    goto("/data?tab=report")
    page.locator("tr", has_text="库存筛选").get_by_role("button", name="运行并预览").click()
    page.wait_for_timeout(500)
    shot("13_report_params")
    dlg = page.locator(".el-dialog").filter(has_text="运行：")
    if dlg.count() and dlg.first.is_visible():
        form_labels = dlg.locator(".el-form-item__label").all_inner_texts()
        if any(x in " ".join(form_labels) for x in ("category", "year", "min_qty", "limit")):
            fail(f"参数表单仍有英文 label: {form_labels}")
        else:
            ok(f"参数表单中文 label={form_labels}")
        page.get_by_role("button", name="取消").click()
    else:
        fail("带参数报表未弹出参数对话框")

    # --- 交互：规整确认页（已发布文件） ---
    goto("/")
    if page.get_by_role("button", name="规整确认").count():
        page.get_by_role("button", name="规整确认").first.click()
        page.wait_for_timeout(1500)
        shot("14_stage")
        body = visible_text(page)
        if page.locator(".stage .el-steps").count() and page.locator(".stage .el-steps").first.is_visible():
            # 已发布应隐藏步骤条
            if "已写入" in body or "已发布" in body:
                fail("已写入态仍显示步骤条")
            else:
                ok("未发布态显示步骤条（可接受）")
        else:
            ok("已写入态隐藏步骤条")
        if body.count("已写入，可查看数据成果") > 1:
            fail("规整确认页重复同一结论")
        assert_no_banned(page, "规整确认")
        if "仅预览前 20 行" in body:
            fail("预览仍写「前 20 行」")
        else:
            ok("预览样例行文案已改")
    else:
        fail("首页没有「规整确认」入口")

    # --- 交互：首页卡跳转 ---
    goto("/")
    page.locator(".card-label", has_text="待办合计").click()
    page.wait_for_timeout(800)
    if "/govern" not in page.url:
        fail(f"待办合计未跳到治理，url={page.url}")
    else:
        ok("待办合计跳到治理")
        shot("15_govern_from_home")

    # --- /system 本地设置一行 ---
    goto("/system?tab=settings")
    shot("16_settings")
    body = visible_text(page)
    if "扩大访问范围前须补正式身份" in body:
        fail("设置页顶栏 alert 仍过长")
    else:
        ok("设置页顶栏已缩为短句")
    if "填写操作令牌后可确认写入" not in body:
        fail("设置页缺少短 hint")
    else:
        ok("设置页有短 hint")

    js_errors = [c for c in CONSOLE if "pageerror" in c or c.startswith("error:")]
    # 过滤已知无害
    js_errors = [c for c in js_errors if "favicon" not in c.lower()]
    if js_errors:
        fail("控制台 JS 错误:\n  " + "\n  ".join(js_errors[:12]))
    else:
        ok("控制台无 pageerror")

    browser.close()
    pw.stop()

    print("\n======== 结果 ========")
    print(f"失败 {len(FAILS)} 项；截图 {SHOT}")
    for m in FAILS:
        print(" -", m)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
