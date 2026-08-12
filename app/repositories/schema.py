# -*- coding: utf-8 -*-
"""Business DuckDB schema (star model + release lineage)."""
from __future__ import annotations

import duckdb

STAR_DDL = [
    """
    CREATE TABLE IF NOT EXISTS dim_material (
        material_id VARCHAR PRIMARY KEY,
        material_code VARCHAR,
        material_name VARCHAR,
        spec VARCHAR,
        unit VARCHAR,
        category VARCHAR,
        name_alias VARCHAR,
        spec_alias VARCHAR,
        source_file VARCHAR,
        code_source VARCHAR,
        match_level VARCHAR,
        source_release_id VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_inventory (
        inventory_id VARCHAR PRIMARY KEY,
        material_id VARCHAR,
        row_key VARCHAR,
        region VARCHAR,
        category VARCHAR,
        source_file VARCHAR,
        source_era VARCHAR,
        color_flag VARCHAR,
        stock_qty DOUBLE,
        opening_qty DOUBLE,
        quota_qty DOUBLE,
        min_qty DOUBLE,
        temp_qty DOUBLE,
        company_wh_qty DOUBLE,
        age_days DOUBLE,
        unit_cost DOUBLE,
        stock_value DOUBLE,
        unit VARCHAR,
        location VARCHAR,
        custodian VARCHAR,
        -- T1: ledger-export-plan §7.1 (LD-1 锁定 2026-08-10)
        remark VARCHAR,
        belong_system VARCHAR,
        project_name VARCHAR,
        consumption_plan VARCHAR,
        material_source VARCHAR,
        group_code VARCHAR,
        is_frame_material VARCHAR,
        agreement_supplier VARCHAR,
        frame_material_code VARCHAR,
        frame_material_name VARCHAR,
        frame_material_spec VARCHAR,
        frame_material_supplier VARCHAR,
        emergency_supplier VARCHAR,
        source_sheet VARCHAR,
        source_release_id VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_asset (
        asset_code VARCHAR PRIMARY KEY,
        asset_name VARCHAR,
        row_key VARCHAR,
        company VARCHAR,
        domain VARCHAR,
        user_name VARCHAR,
        manager VARCHAR,
        location VARCHAR,
        purchase_date VARCHAR,
        status VARCHAR,
        check_result VARCHAR,
        -- T1: ledger-export-plan §7.2 (LD-1/LD-2 锁定 2026-08-10)
        material_code VARCHAR,
        asset_qty DOUBLE,
        unit VARCHAR,
        is_instrument VARCHAR,
        replace_cycle DOUBLE,
        check_cycle DOUBLE,
        consumption_plan VARCHAR,
        tool_source VARCHAR,
        asset_quota_qty DOUBLE,
        remark VARCHAR,
        source_file VARCHAR,
        color_flag VARCHAR,
        source_sheet VARCHAR,
        source_release_id VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_demand (
        demand_id VARCHAR PRIMARY KEY,
        material_id VARCHAR,
        row_key VARCHAR,
        demand_period VARCHAR,
        quantity DOUBLE,
        unit_price DOUBLE,
        total_price DOUBLE,
        unit VARCHAR,
        reporter VARCHAR,
        remark VARCHAR,
        source_file VARCHAR,
        source_release_id VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_quota_adjust (
        quota_id VARCHAR PRIMARY KEY,
        material_id VARCHAR,
        row_key VARCHAR,
        adjust_type VARCHAR,
        material_code VARCHAR,
        material_name VARCHAR,
        installed_qty DOUBLE,
        accident_quota DOUBLE,
        reserve_quota DOUBLE,
        verified_quota DOUBLE,
        device_name VARCHAR,
        reason VARCHAR,
        delete_flag VARCHAR,
        source_file VARCHAR,
        source_release_id VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_stock_flow (
        flow_id VARCHAR PRIMARY KEY,
        material_id VARCHAR,
        row_key VARCHAR,
        flow_type VARCHAR,
        flow_date VARCHAR,
        quantity DOUBLE,
        unit VARCHAR,
        person VARCHAR,
        purpose VARCHAR,
        remark VARCHAR,
        parse_level VARCHAR,
        parse_source VARCHAR,
        source_file VARCHAR,
        source_sheet VARCHAR,
        source_row BIGINT,
        source_segment INTEGER,
        source_release_id VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_release_rows (
        source_release_id VARCHAR NOT NULL,
        file_id VARCHAR NOT NULL,
        target_domain VARCHAR NOT NULL,
        row_key VARCHAR NOT NULL,
        payload_json VARCHAR NOT NULL,
        created_at TIMESTAMP DEFAULT current_timestamp,
        PRIMARY KEY (source_release_id, row_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS write_checkpoint (
        release_id VARCHAR PRIMARY KEY,
        row_count BIGINT NOT NULL,
        target_table VARCHAR,
        updated_at TIMESTAMP DEFAULT current_timestamp
    )
    """,
]

DOMAIN_TABLE = {
    "inventory": "fact_inventory",
    "asset": "fact_asset",
    "demand": "fact_demand",
    "quota": "fact_quota_adjust",
    "stock_flow": "fact_stock_flow",
    "material": "dim_material",
    "generic": "fact_release_rows",
}


def ensure_biz_schema(con: duckdb.DuckDBPyConnection) -> None:
    for ddl in STAR_DDL:
        con.execute(ddl)
    # Add lineage column on legacy-imported tables if missing
    for table in (
        "dim_material",
        "fact_inventory",
        "fact_asset",
        "fact_demand",
        "fact_quota_adjust",
        "fact_stock_flow",
    ):
        cols = {
            r[0]
            for r in con.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema='main' AND table_name=?
                """,
                [table],
            ).fetchall()
        }
        if "source_release_id" not in cols:
            con.execute(f"ALTER TABLE {table} ADD COLUMN source_release_id VARCHAR")
        if "row_key" not in cols:
            con.execute(f"ALTER TABLE {table} ADD COLUMN row_key VARCHAR")
    # fact_stock_flow column upgrades (docs/12 §2)
    flow_cols = {
        r[0]
        for r in con.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='main' AND table_name='fact_stock_flow'
            """
        ).fetchall()
    }
    for col, typ in (
        ("remark", "VARCHAR"),
        ("parse_level", "VARCHAR"),
        ("parse_source", "VARCHAR"),
        ("source_sheet", "VARCHAR"),
        ("source_segment", "INTEGER"),
    ):
        if flow_cols and col not in flow_cols:
            con.execute(f"ALTER TABLE fact_stock_flow ADD COLUMN {col} {typ}")
    # source_row may exist as VARCHAR — leave as-is for DuckDB compatibility
    # write_checkpoint.target_table migration
    wc_cols = {
        r[0]
        for r in con.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='main' AND table_name='write_checkpoint'
            """
        ).fetchall()
    }
    if wc_cols and "target_table" not in wc_cols:
        con.execute("ALTER TABLE write_checkpoint ADD COLUMN target_table VARCHAR")
    # A7.1 opening balance for reconcile (docs/12 §6); default NULL → treated as 0
    inv_cols = {
        r[0]
        for r in con.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='main' AND table_name='fact_inventory'
            """
        ).fetchall()
    }
    if inv_cols and "opening_qty" not in inv_cols:
        con.execute("ALTER TABLE fact_inventory ADD COLUMN opening_qty DOUBLE")
    # T1: ledger-export-plan §7.1/§7.2 台账业务列（LD-1/LD-2 锁定 2026-08-10，幂等）
    _ledger_cols = {
        "fact_inventory": [
            ("remark", "VARCHAR"),
            ("belong_system", "VARCHAR"),
            ("project_name", "VARCHAR"),
            ("consumption_plan", "VARCHAR"),
            ("material_source", "VARCHAR"),
            ("group_code", "VARCHAR"),
            ("is_frame_material", "VARCHAR"),
            ("agreement_supplier", "VARCHAR"),
            ("frame_material_code", "VARCHAR"),
            ("frame_material_name", "VARCHAR"),
            ("frame_material_spec", "VARCHAR"),
            ("frame_material_supplier", "VARCHAR"),
            ("emergency_supplier", "VARCHAR"),
        ],
        "fact_asset": [
            ("material_code", "VARCHAR"),
            ("asset_qty", "DOUBLE"),
            ("unit", "VARCHAR"),
            ("is_instrument", "VARCHAR"),
            ("replace_cycle", "DOUBLE"),
            ("check_cycle", "DOUBLE"),
            ("consumption_plan", "VARCHAR"),
            ("tool_source", "VARCHAR"),
            ("asset_quota_qty", "DOUBLE"),
            ("remark", "VARCHAR"),
        ],
    }
    for _t, _cols in _ledger_cols.items():
        _tcols = {
            r[0]
            for r in con.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema='main' AND table_name=?
                """,
                [_t],
            ).fetchall()
        }
        for _col, _typ in _cols:
            if _col not in _tcols:
                con.execute(f"ALTER TABLE {_t} ADD COLUMN {_col} {_typ}")
    # T7: ledger-export-plan §7 台账导出报表按 sheet 过滤（LD-5 sheet 标记 2026-08-10）
    for _t in ("fact_inventory", "fact_asset"):
        _tcols = {
            r[0]
            for r in con.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema='main' AND table_name=?
                """,
                [_t],
            ).fetchall()
        }
        if "source_sheet" not in _tcols:
            con.execute(f"ALTER TABLE {_t} ADD COLUMN source_sheet VARCHAR")
    con.execute(
        """
        CREATE OR REPLACE VIEW v_material_inventory AS
        SELECT m.material_name, m.material_code, m.spec, i.region,
               i.stock_qty, i.opening_qty, i.quota_qty, i.location, i.source_era, i.source_file,
               i.source_release_id
        FROM fact_inventory i
        LEFT JOIN dim_material m USING (material_id)
        """
    )
    # DT-W1: 业务明细视图（question/14 §3.1）——browse 默认 mode=business 时的宽表：
    # 名称/规格/单位前置（JOIN dim_material），material_id 置后列供溯源；不重复库表结构。
    con.execute(
        """
        CREATE OR REPLACE VIEW v_browse_inventory AS
        SELECT m.material_name, m.spec, m.unit,
               i.region, i.category, i.stock_qty, i.opening_qty, i.quota_qty, i.min_qty,
               i.temp_qty, i.company_wh_qty, i.unit_cost, i.stock_value, i.age_days,
               i.location, i.custodian, i.remark, i.belong_system, i.project_name,
               i.consumption_plan, i.material_source, i.group_code, i.is_frame_material,
               i.agreement_supplier, i.frame_material_code, i.frame_material_name,
               i.frame_material_spec, i.frame_material_supplier, i.emergency_supplier,
               i.material_id, i.source_file, i.source_release_id, i.row_key
        FROM fact_inventory i
        LEFT JOIN dim_material m USING (material_id)
        """
    )
    con.execute(
        """
        CREATE OR REPLACE VIEW v_browse_stock_flow AS
        SELECT m.material_name, m.spec, m.unit,
               f.flow_type, f.flow_date, f.quantity, f.person, f.purpose, f.remark,
               f.material_id, f.source_file, f.source_release_id, f.row_key
        FROM fact_stock_flow f
        LEFT JOIN dim_material m USING (material_id)
        """
    )
    con.execute(
        """
        CREATE OR REPLACE VIEW v_browse_demand AS
        SELECT m.material_name, m.spec, m.unit,
               d.demand_period, d.quantity, d.unit_price, d.total_price, d.reporter, d.remark,
               d.material_id, d.source_file, d.source_release_id, d.row_key
        FROM fact_demand d
        LEFT JOIN dim_material m USING (material_id)
        """
    )
    con.execute(
        """
        CREATE OR REPLACE VIEW v_browse_asset AS
        SELECT a.asset_name, a.asset_code, a.material_code, a.asset_qty, a.unit, a.status,
               a.check_result, a.user_name, a.manager, a.location, a.domain, a.company,
               a.purchase_date, a.is_instrument, a.replace_cycle, a.check_cycle,
               a.tool_source, a.asset_quota_qty, a.consumption_plan, a.remark,
               a.source_file, a.source_release_id, a.row_key
        FROM fact_asset a
        """
    )
