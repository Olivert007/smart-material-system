# -*- coding: utf-8 -*-
"""CSV 导出侧安全工具（roadmap/csv-export-harden.md T2）。

导出链路统一使用：
- ``sanitize_csv_cell``：对以 ``= + - @``（含制表符/回车）开头的单元格前置 ``'``，
  Excel 按文本而非公式解析（防 CSV 公式注入）；仅命中危险前缀的单元格被改写，其余原样。
- ``sanitize_df``：整表净化（pandas 版本差异兜底：老版本无 ``DataFrame.map`` 用 ``applymap``）。
- ``csv_bom``：UTF-8 BOM（``\\ufeff``），Excel 双击打开中文不乱码。

本模块为导出侧工具，不依赖业务逻辑，不写回 DuckDB 标准表。
"""
from __future__ import annotations

# Excel 公式注入危险前缀（OpenFormula）：等号/加号/减号/at 及制表符、回车
_DANGEROUS_PREFIX = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_cell(v: object) -> str:
    """净化单个 CSV 单元格：危险前缀前置 ``'``，空值保留空串，其余原样。"""
    if v is None:
        return ""
    s = str(v)
    if s.startswith(_DANGEROUS_PREFIX):
        return "'" + s
    return s


def sanitize_df(df):
    """整表净化（T2.2 / T2.3 共用）；空表原样返回。"""
    if df is None or len(df) == 0:
        return df
    _map = getattr(df, "map", None) or getattr(df, "applymap")
    return _map(sanitize_csv_cell)


def csv_bom() -> str:
    """UTF-8 BOM 前缀（T1 各链路共用）。"""
    return "\ufeff"
