# 字段映射记忆（rule_dict）

来源：meta.sqlite · rule_dict。人工确认后的表头→标准字段映射。

| 表头 | 业务域 | 标准字段 | 命中次数 | 来源 | 确认人 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 单价 | default | unit_cost | 1 | seed | system:seed | active |
| 填报人 | default | keeper_or_user | 1 | seed | system:seed | active |
| 外部ID列 | default | ignore | 1 | map_pending_confirm | tester | active |
| 外部追踪号ZZ99 | default | remark | 1 | map_pending_confirm | tester | active |
| 模糊列 | default | region | 2 | human_confirm | t | active |
| 模糊列 | default | location | 2 | human_confirm | t | active |
| qty_in | default | qty_in | 1 | map_pending_confirm | ops | active |
| flow_out_text | default | flow_out_text | 1 | map_pending_confirm | ops | active |
| 领用记录 | default | ignore | 1 | map_pending_confirm | ops | active |
| 行号 | default | ignore | 1 | map_pending_confirm | ops | active |
| 图号 | default | ignore | 1 | map_pending_confirm | ops | active |
| 会计组描述 | default | ignore | 1 | map_pending_confirm | ops | active |
| 会计组 | default | ignore | 1 | map_pending_confirm | ops | active |
| flow_in_text | default | flow_in_text | 1 | map_pending_confirm | ops | active |
| temp_qty | default | temp_qty | 1 | map_pending_confirm | system | active |
| storage_time | default | storage_time | 1 | map_pending_confirm | system | active |
| spec | default | spec | 1 | map_pending_confirm | system | active |
| sheet | default | source_sheet | 1 | map_pending_confirm | system | active |
| remaining_temp_qty | default | remaining_temp_qty | 1 | map_pending_confirm | system | active |
| material_name | default | material_name | 1 | map_pending_confirm | system | active |
| 存放货位 | default | location | 1 | map_pending_confirm | system | active |
| 扫描 | default | ignore | 1 | map_pending_confirm | ops | active |
