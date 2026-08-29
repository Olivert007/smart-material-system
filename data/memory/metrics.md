# 指标口径（metric_dict）

来源：meta.sqlite · metric_dict。

| 指标 ID | 指标名称 | 状态 | SQL 口径 | 单位 | 别名 |
| --- | --- | --- | --- | --- | --- |
| ASSET_COUNT_TOTAL | 资产总数 | active | SELECT COUNT(*) AS v FROM fact_asset WHERE COALESCE(status, '') NOT LIKE '%待报废%' | 台 | ["资产合计", "资产台数", "资产总数是多少", "有多少资产"] |
| ASSET_MISSING_MANAGER_CNT | 缺保管人资产数 | active | SELECT COUNT(*) AS v FROM fact_asset WHERE manager IS NULL OR TRIM(manager) = '' | 台 | ["缺少保管人", "缺保管人", "无保管人", "缺少保管人的资产有多少"] |
| DEMAND_QTY_TOTAL | 需求总量 | active | SELECT SUM(quantity) AS v FROM fact_demand | 件 | ["需求合计", "需求总数", "需求总量是多少", "需求数量合计"] |
| FLOW_IN_QTY_TOTAL | 入库流水合计 | active | SELECT SUM(quantity) AS v FROM fact_stock_flow WHERE flow_type='IN' | 件 | ["入库合计", "入库流水总量", "本期入库量"] |
| FLOW_OUT_QTY_TOTAL | 出库流水合计 | active | SELECT SUM(quantity) AS v FROM fact_stock_flow WHERE flow_type='OUT' | 件 | ["出库合计", "出库流水总量", "本期出库量"] |
| FLOW_PARSE_L1_RATIO | 流水解析 L1 占比 | active | SELECT CASE WHEN COUNT(*) FILTER (WHERE parse_level IN ('L1','L2')) = 0 THEN NULL ELSE CAST(COUNT(*) FILTER (WHERE parse_level='L1') AS DOUBLE) / COUNT(*) FILTER (WHERE parse_level IN ('L1','L2')) END AS v FROM fact_stock_flow | ratio | ["L1占比", "流水L1比例"] |
| FLOW_QTY_TOTAL | 流水入库合计（质量门） | active | SELECT SUM(quantity) AS v FROM fact_stock_flow WHERE flow_type='IN' | 件 | ["流水入库合计"] |
| FLOW_RECONCILE_GAP_CNT | 勾稽差异行数 | active | SELECT COUNT(*) AS v FROM flow_reconcile_gap | 行 | ["勾稽差异数", "流水勾稽gap"] |
| INTAKE_BLOCK_RATE | 接入阻断率 | active | SELECT CASE WHEN (COALESCE(clean_rows,0)+COALESCE(blocked_rows,0))=0 THEN 0.0 ELSE CAST(COALESCE(blocked_rows,0) AS REAL)/(COALESCE(clean_rows,0)+COALESCE(blocked_rows,0)) END AS v FROM staging_record ORDER BY updated_at DESC LIMIT 1 | ratio | ["阻断率", "blocked率", "清洗阻断比例"] |
| INTAKE_CLEAN_RATE | 接入清洁率 | active | SELECT CASE WHEN (COALESCE(clean_rows,0)+COALESCE(blocked_rows,0))=0 THEN 1.0 ELSE CAST(COALESCE(clean_rows,0) AS REAL)/(COALESCE(clean_rows,0)+COALESCE(blocked_rows,0)) END AS v FROM staging_record ORDER BY updated_at DESC LIMIT 1 | ratio | ["清洁率", "clean率"] |
| INV_BELOW_MIN_CNT | 低于最低库存物资数 | active | SELECT COUNT(*) AS v FROM fact_inventory WHERE min_qty IS NOT NULL AND stock_qty IS NOT NULL AND stock_qty < min_qty | 种 | ["最低库存预警", "低于最低库存", "库存不足", "缺货预警"] |
| INV_EMERGENCY_QUOTA_FILL_RATIO | 应急备汛定额利用率 | active | SELECT CASE WHEN SUM(CASE WHEN quota_qty > 0 THEN quota_qty ELSE 0 END) = 0 THEN NULL ELSE CAST(SUM(CASE WHEN quota_qty > 0 THEN stock_qty ELSE 0 END) AS DOUBLE) / SUM(CASE WHEN quota_qty > 0 THEN quota_qty ELSE 0 END) END AS v FROM fact_inventory WHERE source_sheet='应急备汛物资' | ratio | ["应急备汛定额比", "应急物资定额利用率", "备汛定额满足率"] |
| INV_MISSING_LOCATION_CNT | 缺库位库存行数 | active | SELECT COUNT(*) AS v FROM fact_inventory WHERE location IS NULL OR TRIM(location) = '' | 行 | ["缺少库位", "缺库位", "无库位", "缺少库位的库存有多少"] |
| INV_OVER_QUOTA_CNT | 超定额物资数 | active | SELECT COUNT(*) AS v FROM fact_inventory WHERE quota_qty IS NOT NULL AND stock_qty IS NOT NULL AND stock_qty > quota_qty | 种 | ["超定额", "超定额物资", "超定额有多少", "超过定额的物资数"] |
| INV_QTY_TOTAL | 库存总数量 | active | SELECT CASE WHEN COUNT(DISTINCT COALESCE(NULLIF(TRIM(unit), ''), '<空>')) > 1 THEN NULL ELSE SUM(stock_qty) END AS v FROM fact_inventory |  | ["库存总量", "库存合计", "现有库存合计", "库存总数量是多少"] |
| INV_QUOTA_FILL_RATIO | 定额利用率 | active | SELECT CASE WHEN SUM(CASE WHEN quota_qty > 0 THEN quota_qty ELSE 0 END) = 0 THEN NULL ELSE CAST(SUM(CASE WHEN quota_qty > 0 THEN stock_qty ELSE 0 END) AS DOUBLE) / SUM(CASE WHEN quota_qty > 0 THEN quota_qty ELSE 0 END) END AS v FROM fact_inventory | ratio | ["定额比", "库存定额比", "定额利用率", "库存占定额比例"] |
| INV_RECORD_CNT | 库存记录行数 | active | SELECT COUNT(*) AS v FROM fact_inventory | 行 | ["库存表有多少行", "库存记录数", "库存行数", "库存记录条数"] |
| INV_STALE_CNT | 呆滞料行数 | active | SELECT CASE WHEN SUM(CASE WHEN age_days IS NOT NULL THEN 1 ELSE 0 END) = 0 THEN NULL ELSE SUM(CASE WHEN age_days >= 365 THEN 1 ELSE 0 END) END AS v FROM fact_inventory | 行 | ["呆滞料", "呆滞库存", "超龄库存", "呆滞料有多少"] |
| INV_VALUE_TOTAL | 库存总金额 | active | SELECT SUM(stock_value) AS v FROM fact_inventory WHERE stock_value IS NOT NULL | 元 | ["库存金额合计", "库存总额", "库存总金额是多少", "存货金额"] |
| INV_ZERO_STOCK_CNT | 零库存物资数 | active | SELECT COUNT(*) AS v FROM fact_inventory WHERE stock_qty IS NULL OR stock_qty = 0 | 种 | ["零库存", "库存为0", "库存为零", "零库存物资有多少"] |
