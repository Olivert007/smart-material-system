# -*- coding: utf-8 -*-
"""标准表/字段中文名与技术字段定义（业务分析视角）。

供导出端点与业务表格做「汉化 + 隐藏技术字段」：
- table_zh / field_zh：把库级表名/字段名映射为业务中文名；
- TECHNICAL_FIELDS：溯源/解析/治理类技术字段，业务导出与展示时隐藏；
- 隐藏字段是「导出展示层」处理，DuckDB 标准表结构不变（zh=0 可拿原始列）。
"""
from __future__ import annotations

TABLE_ZH = {
    "dim_material": "物资主数据",
    "fact_inventory": "库存台账",
    "fact_asset": "资产台账",
    "fact_demand": "需求明细",
    "fact_quota_adjust": "定额调整记录",
    "fact_stock_flow": "出入库流水",
    "v_material_inventory": "物资库存视图",
    "v_browse_inventory": "库存台账（业务明细）",
    "v_browse_stock_flow": "出入库流水（业务明细）",
    "v_browse_demand": "需求明细（业务明细）",
    "v_browse_asset": "资产台账（业务明细）",
}

FIELD_ZH = {
    # 通用
    "material_id": "物资ID",
    "material_code": "物资编码",
    "material_name": "物资名称",
    "unit": "单位",
    "category": "类别",
    "spec": "规格型号",
    "source_file": "来源文件",
    # dim_material
    "name_alias": "名称别名",
    "spec_alias": "规格别名",
    "code_source": "编码来源",
    # fact_inventory
    "inventory_id": "库存ID",
    "region": "区域",
    "stock_qty": "库存数量",
    "opening_qty": "期初数量",
    "quota_qty": "定额数量",
    "min_qty": "最低数量",
    "temp_qty": "临时数量",
    "company_wh_qty": "公司仓数量",
    # ZW 台账（新模板）扩展列（rpt_ledger_zw 报表列头汉化）
    "storage_time": "物资储存时间",
    "remaining_temp_qty": "剩余临时储存数量",
    "age_days": "库龄(天)",
    "unit_cost": "单价",
    "stock_value": "库存金额",
    "location": "库位",
    "custodian": "库管员",
    # T1/T2: ledger-export-plan §7.1（LD-1 锁定 2026-08-10）
    "belong_system": "所属系统",
    "project_name": "项目名称",
    "consumption_plan": "消耗计划",
    "material_source": "物资来源",
    "group_code": "新集团编码",
    "is_frame_material": "是否框架物资",
    "agreement_supplier": "协议供应商",
    "frame_material_code": "推荐框架物资编码",
    "frame_material_name": "推荐框架物资名称",
    "frame_material_spec": "推荐框架物资型号",
    "frame_material_supplier": "推荐框架物资供应商",
    "emergency_supplier": "应急供应商",
    # fact_asset
    "asset_code": "资产编号",
    "asset_name": "资产名称",
    "company": "所属单位",
    "domain": "业务域",
    "user_name": "使用人",
    "manager": "管理人",
    "purchase_date": "购置日期",
    "status": "状态",
    "check_result": "盘点结果",
    # T1/T2: ledger-export-plan §7.2（LD-1/LD-2 锁定 2026-08-10）
    "asset_qty": "资产数量",
    "is_instrument": "是否仪器仪表",
    "replace_cycle": "更换周期(年)",
    "check_cycle": "检测周期(年)",
    "tool_source": "工器具来源",
    "asset_quota_qty": "资产定额数量",
    # fact_demand
    "demand_id": "需求ID",
    "demand_period": "需求期间",
    "quantity": "数量",
    "unit_price": "单价",
    "total_price": "需求金额",
    "reporter": "申报人",
    "remark": "备注",
    # fact_quota_adjust
    "quota_id": "调整ID",
    "adjust_type": "调整类型",
    "installed_qty": "装机数量",
    "accident_quota": "事故定额",
    "reserve_quota": "储备定额",
    "verified_quota": "核定定额",
    "device_name": "设备名称",
    "reason": "原因",
    # fact_stock_flow
    "flow_id": "流水ID",
    "flow_type": "出入类型",
    "flow_date": "日期",
    "person": "经手人",
    "purpose": "用途",
    # 宽表出入库列（台账/导出常用，映射建议与待确认字段展示）
    "flow_in_text": "入库记录",
    "qty_in": "入库数量",
    "flow_out_text": "出库记录",
    "qty_out": "出库数量",
    # embed_recall.STD_FIELDS 别名键（与库表字段名并存，下拉展示用）
    "item_name": "物资名称",
    "specification": "规格型号",
    "department": "所属部门",
    "keeper_or_user": "保管/使用人",
    "serial_or_factory_no": "出厂编号",
}

# 溯源/解析/治理类技术字段：业务表格与导出中隐藏（zh=0 可还原）
TECHNICAL_FIELDS = {
    "source_release_id",
    "row_key",
    "source_era",
    "color_flag",
    "delete_flag",
    "parse_level",
    "parse_source",
    "source_sheet",
    "source_row",
    "source_segment",
    "match_level",
}

# 枚举值汉化（U-6）：仅影响展示层，库值保持 IN/OUT 等原始编码
VALUE_ZH = {
    "flow_type": {"IN": "入库", "OUT": "出库"},
    # fact_demand：源表缺「需求期间」列时 mapping 兜底为 unknown，展示层汉化
    "demand_period": {"unknown": "未填写"},
}

# 按表覆盖的字段中文名（优先级高于 FIELD_ZH，用于同名不同域时区分）
TABLE_FIELD_ZH: dict[str, dict[str, str]] = {
    "fact_inventory": {
        "location": "库位",
        "custodian": "库管员",
        "stock_qty": "库存数量",
        "opening_qty": "期初数量",
        "quota_qty": "定额数量",
        "min_qty": "最低库存",
        "company_wh_qty": "公司仓数量",
        "belong_system": "所属系统",
        "project_name": "项目名称",
        "consumption_plan": "消耗计划",
        "material_source": "物资来源",
        "group_code": "新集团编码",
        "is_frame_material": "是否框架物资",
        "agreement_supplier": "协议供应商",
        "frame_material_code": "推荐框架物资编码",
        "frame_material_name": "推荐框架物资名称",
        "frame_material_spec": "推荐框架物资型号",
        "frame_material_supplier": "推荐框架物资供应商",
        "emergency_supplier": "应急供应商",
    },
    "fact_asset": {
        "location": "存放位置",
        "user_name": "使用人",
        "manager": "管理人",
        "check_result": "盘点结果",
        "asset_qty": "数量",
        "asset_quota_qty": "定额数量",
        "material_code": "物资编码",
        "is_instrument": "是否仪器仪表",
        "replace_cycle": "更换周期(年)",
        "check_cycle": "检测周期(年)",
        "tool_source": "工器具来源",
        "consumption_plan": "消耗计划",
        "remark": "备注",
    },
    "fact_stock_flow": {
        "person": "经手人",
        "purpose": "用途",
        "quantity": "数量",
    },
    "fact_demand": {
        "reporter": "申报人",
        "quantity": "需求数量",
    },
}


def table_zh(table: str) -> str:
    return TABLE_ZH.get(table, table)


def field_zh(field: str) -> str:
    return FIELD_ZH.get(field, field)


def table_field_zh(table: str, field: str) -> str:
    """按表字段中文名：优先 TABLE_FIELD_ZH[table]，其次全局 FIELD_ZH。"""
    return (TABLE_FIELD_ZH.get(table) or {}).get(field, FIELD_ZH.get(field, field))


def table_zh_columns(table: str, columns: list[str]) -> list[str]:
    """按表汉化列名（未在字典中的保持原名）。"""
    return [table_field_zh(table, c) for c in columns]


def value_zh(field: str, value):
    """枚举值汉化（U-6）：flow_type IN→入库、OUT→出库；无映射时原样返回。"""
    mp = VALUE_ZH.get(field)
    if mp is None or value is None:
        return value
    return mp.get(str(value), value)


def is_technical(field: str) -> bool:
    return field in TECHNICAL_FIELDS


def visible_fields(columns: list[str]) -> list[str]:
    """过滤技术字段后的业务列。"""
    return [c for c in columns if not is_technical(c)]


def zh_columns(columns: list[str]) -> list[str]:
    """列名汉化（未在字典中的保持原名）。"""
    return [FIELD_ZH.get(c, c) for c in columns]


def zh_columns_for_table(table: str, columns: list[str]) -> list[str]:
    """按物理表汉化列名（U-6 / DT-W6）：有 TABLE_FIELD_ZH 时优先按表映射。"""
    if table in TABLE_FIELD_ZH:
        return table_zh_columns(table, columns)
    return zh_columns(columns)
