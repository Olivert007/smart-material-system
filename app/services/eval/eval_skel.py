# -*- coding: utf-8 -*-
"""Stage 1 eval skeleton (docs/10). Expand toward minima before Stage 2."""
from __future__ import annotations

import json
from pathlib import Path

from app import config

MAP_SAMPLES = [
    {
        "headers": ["物资编码", "物资名称", "现有数量", "库位号"],
        "expect": {
            "物资编码": "material_code",
            "物资名称": "item_name",
            "现有数量": "stock_qty",
            "库位号": "location",
        },
    },
    {
        "headers": ["资产编号", "名称", "规格型号", "使用人"],
        "expect": {
            "资产编号": "asset_code",
            "名称": "item_name",
            "规格型号": "specification",
            "使用人": "keeper_or_user",
        },
    },
    {
        "headers": ["编码", "品名", "数量", "单位", "存放位置"],
        "expect": {
            "编码": "material_code",
            "品名": "item_name",
            "数量": "stock_qty",
            "单位": "unit",
            "存放位置": "location",
        },
    },
    {
        "headers": ["物资名称", "型号规格", "统一现有数量", "库位号", "物资大类"],
        "expect": {
            "物资名称": "item_name",
            "型号规格": "specification",
            "统一现有数量": "stock_qty",
            "库位号": "location",
            "物资大类": "category",
        },
    },
    {
        "headers": ["资产编码", "资产名称", "公司", "使用人姓名", "位置描述"],
        "expect": {
            "资产编码": "asset_code",
            "资产名称": "item_name",
            "公司": "company",
            "使用人姓名": "keeper_or_user",
            "位置描述": "location",
        },
    },
    {
        "headers": ["实物资产编码", "实物资产名称", "管理者姓名", "出厂编号"],
        "expect": {
            "实物资产编码": "asset_code",
            "实物资产名称": "item_name",
            "管理者姓名": "keeper_or_user",
            "出厂编号": "serial_or_factory_no",
        },
    },
    {
        "headers": ["物资名称", "数量", "单位", "填报人", "合价（元）"],
        "expect": {
            "物资名称": "item_name",
            "数量": "quantity",
            "单位": "unit",
            "填报人": "keeper_or_user",
            "合价（元）": "stock_value",
        },
    },
    {
        "headers": ["物料编码", "物料名称", "账面数量", "库位", "部门"],
        "expect": {
            "物料编码": "material_code",
            "物料名称": "item_name",
            "账面数量": "stock_qty",
            "库位": "location",
            "部门": "department",
        },
    },
    {
        "headers": ["区域", "分类", "现有库存", "定额", "备注"],
        "expect": {
            "区域": "region",
            "分类": "category",
            "现有库存": "stock_qty",
            "定额": "quota_qty",
            "备注": "remark",
        },
    },
    {
        "headers": ["期次", "物资编码", "需求数量", "单价"],
        "expect": {
            "期次": "demand_period",
            "物资编码": "material_code",
            "需求数量": "quantity",
            "单价": "stock_value",
        },
    },
]

SQL_SAMPLES = [
    {
        "question": "库存表有多少行",
        "must_contain": [
            "fact_inventory",
            "count"
        ],
        "expect_min_rows": 1
    },
    {
        "question": "列出物资主数据前5条名称",
        "must_contain": [
            "dim_material",
            "limit"
        ],
        "expect_min_rows": 1
    },
    {
        "question": "按库位统计库存记录数，取前10",
        "must_contain": [
            "fact_inventory",
            "location",
            "group"
        ],
        "expect_min_rows": 1
    },
    {
        "question": "现有数量大于100的库存有哪些，最多20条",
        "must_contain": [
            "fact_inventory",
            "stock_qty"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "资产表有多少行",
        "must_contain": [
            "fact_asset",
            "count"
        ],
        "expect_min_rows": 1
    },
    {
        "question": "需求表有多少行",
        "must_contain": [
            "fact_demand",
            "count"
        ],
        "expect_min_rows": 1
    },
    {
        "question": "库存数量最高的前5条",
        "must_contain": [
            "fact_inventory",
            "stock_qty",
            "order",
            "limit"
        ],
        "expect_min_rows": 1
    },
    {
        "question": "按物资大类统计库存行数",
        "must_contain": [
            "fact_inventory",
            "category",
            "group"
        ],
        "expect_min_rows": 1
    },
    {
        "question": "列出资产名称包含电平的记录，最多10条",
        "must_contain": [
            "fact_asset",
            "like"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "需求数量合计是多少",
        "must_contain": [
            "fact_demand",
            "sum"
        ],
        "expect_min_rows": 1
    },
    {
        "question": "库存数量合计是多少",
        "must_contain": [
            "fact_inventory",
            "sum",
            "stock_qty"
        ],
        "expect_min_rows": 1
    },
    {
        "question": "库存金额合计是多少",
        "must_contain": [
            "fact_inventory",
            "sum",
            "stock_value"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "定额数量合计是多少",
        "must_contain": [
            "fact_inventory",
            "sum",
            "quota_qty"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "按区域统计库存行数",
        "must_contain": [
            "fact_inventory",
            "region",
            "group"
        ],
        "expect_min_rows": 1
    },
    {
        "question": "按类别统计库存数量合计",
        "must_contain": [
            "fact_inventory",
            "category",
            "sum"
        ],
        "expect_min_rows": 1
    },
    {
        "question": "库存数量为空的行有多少",
        "must_contain": [
            "fact_inventory",
            "stock_qty"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "列出库存库位前20个不重复值",
        "must_contain": [
            "fact_inventory",
            "location"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "库存表有哪些字段相关的行数查询",
        "must_contain": [
            "fact_inventory",
            "count"
        ],
        "expect_min_rows": 1
    },
    {
        "question": "期初数量合计",
        "must_contain": [
            "fact_inventory",
            "opening_qty"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "超定额库存有多少行",
        "must_contain": [
            "fact_inventory",
            "stock_qty",
            "quota_qty"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "呆滞库存 age_days 大于365的行数",
        "must_contain": [
            "fact_inventory",
            "age_days"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "按库位汇总库存金额前10",
        "must_contain": [
            "fact_inventory",
            "location",
            "group"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "物资主数据有多少行",
        "must_contain": [
            "dim_material",
            "count"
        ],
        "expect_min_rows": 1
    },
    {
        "question": "列出物资编码前10条",
        "must_contain": [
            "dim_material",
            "material_code",
            "limit"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "物资名称包含轴承的主数据，最多15条",
        "must_contain": [
            "dim_material",
            "like"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "按类别统计主数据行数",
        "must_contain": [
            "dim_material",
            "category",
            "group"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "资产状态分布统计",
        "must_contain": [
            "fact_asset",
            "status",
            "group"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "资产按公司统计数量",
        "must_contain": [
            "fact_asset",
            "company",
            "group"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "资产按位置统计行数",
        "must_contain": [
            "fact_asset",
            "location",
            "group"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "列出资产编码前10条",
        "must_contain": [
            "fact_asset",
            "asset_code",
            "limit"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "资产名称包含泵的记录",
        "must_contain": [
            "fact_asset",
            "like"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "待报废资产有多少",
        "must_contain": [
            "fact_asset",
            "status"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "需求数量最高的前10条",
        "must_contain": [
            "fact_demand",
            "quantity",
            "order",
            "limit"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "按需求期次统计行数",
        "must_contain": [
            "fact_demand",
            "demand_period",
            "group"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "需求总价合计",
        "must_contain": [
            "fact_demand",
            "sum"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "列出需求填报人前10个",
        "must_contain": [
            "fact_demand",
            "limit"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "流水表有多少行",
        "must_contain": [
            "fact_stock_flow",
            "count"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "入库流水数量合计",
        "must_contain": [
            "fact_stock_flow",
            "sum",
            "quantity"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "出库流水数量合计",
        "must_contain": [
            "fact_stock_flow",
            "sum",
            "quantity"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "按流水类型统计行数",
        "must_contain": [
            "fact_stock_flow",
            "flow_type",
            "group"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "按解析级别 parse_level 统计流水",
        "must_contain": [
            "fact_stock_flow",
            "parse_level",
            "group"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "流水数量最高的前5条",
        "must_contain": [
            "fact_stock_flow",
            "quantity",
            "order",
            "limit"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "定额调整表有多少行",
        "must_contain": [
            "fact_quota_adjust",
            "count"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "库存单位有哪些去重值，最多20",
        "must_contain": [
            "fact_inventory",
            "unit"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "库存保管人字段非空行数",
        "must_contain": [
            "fact_inventory",
            "count"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "按来源文件统计库存行数前10",
        "must_contain": [
            "fact_inventory",
            "source_file",
            "group"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "库存数量小于定额的行数",
        "must_contain": [
            "fact_inventory",
            "stock_qty",
            "quota_qty"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "库存数量等于定额的行数",
        "must_contain": [
            "fact_inventory",
            "stock_qty",
            "quota_qty"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "列出库存 material_id 前20条",
        "must_contain": [
            "fact_inventory",
            "material_id",
            "limit"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "需求 quantity 大于0的行数",
        "must_contain": [
            "fact_demand",
            "quantity"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "资产表 status 为空的行数",
        "must_contain": [
            "fact_asset",
            "status"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "主数据 material_name 非空行数",
        "must_contain": [
            "dim_material",
            "material_name"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "流水 person 字段非空行数",
        "must_contain": [
            "fact_stock_flow",
            "person"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "按 flow_date 统计流水行数",
        "must_contain": [
            "fact_stock_flow",
            "flow_date",
            "group"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "库存 stock_value 不为空的行数",
        "must_contain": [
            "fact_inventory",
            "stock_value"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "库存 temp_qty 合计",
        "must_contain": [
            "fact_inventory",
            "temp_qty"
        ],
        "expect_min_rows": 0
    },
    {
        "question": "需求按 material_id 汇总数量前10",
        "must_contain": [
            "fact_demand",
            "material_id",
            "group"
        ],
        "expect_min_rows": 0
    }
]


def ensure_eval_skeleton(*, force: bool = False) -> Path:
    root = config.EVAL
    root.mkdir(parents=True, exist_ok=True)
    map_path = root / "header_mapping.jsonl"
    sql_path = root / "text2sql.jsonl"
    if force or not map_path.exists():
        with map_path.open("w", encoding="utf-8") as f:
            for row in MAP_SAMPLES:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    if force or not sql_path.exists():
        with sql_path.open("w", encoding="utf-8") as f:
            for row in SQL_SAMPLES:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    from app.services.flow_eval import FLOW_LLM_SAMPLES, ensure_flow_eval

    ensure_flow_eval(force=force)
    readme = root / "README.md"
    readme.write_text(
        "# Eval skeleton (Stage 1)\n\n"
        f"- `header_mapping.jsonl` — {len(MAP_SAMPLES)} mapping gold cases\n"
        f"- `text2sql.jsonl` — {len(SQL_SAMPLES)} SQL smoke checks\n"
        f"- `flow_parse_llm.jsonl` — {len(FLOW_LLM_SAMPLES)} flow suggest gold (docs/12 B4)\n"
        "- `results/` — `scripts/run_eval_stage1.py` / `run_eval_flow.py` / harden outputs\n\n"
        "Docs/10 Stage1 simple SQL baseline: >=50 cases in text2sql.jsonl.\n",
        encoding="utf-8",
    )
    return root
