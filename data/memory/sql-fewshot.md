# 问数样例（sql_fewshot）

来源：meta.sqlite · sql_fewshot。

| 问题 | 问题类型 | SQL | 来源 | 命中次数 |
| --- | --- | --- | --- | --- |
| 库存表有多少行 | count | SELECT COUNT(*) AS row_count FROM fact_inventory | seed | 0 |
| 库存总数量是多少 | metric | SELECT SUM(stock_qty) AS v FROM fact_inventory | seed | 0 |
| 需求总量是多少 | metric | SELECT SUM(quantity) AS v FROM fact_demand | seed | 0 |
