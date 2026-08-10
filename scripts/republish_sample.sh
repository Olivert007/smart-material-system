#!/usr/bin/env bash
# Upload a real sample into the live F2 API (:8010), stage, confirm, verify rows.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API="${API:-http://127.0.0.1:8010}"
TOKEN="${OPS_TOKEN:-dev-ops-token-change-me}"
SAMPLE="${1:-/workspace/2026-07/通信-溪洛渡川云公司CTGCY概览库存中的库存件 260721-95650(1).xlsx}"

if [[ ! -f "$SAMPLE" ]]; then
  echo "sample not found: $SAMPLE" >&2
  exit 1
fi

echo "upload $SAMPLE"
UP=$(curl -sS -X POST "$API/api/v1/files" -F "file=@${SAMPLE}")
echo "$UP" | python3 -m json.tool
FILE_ID=$(python3 -c "import json,sys; print(json.load(sys.stdin)['file_id'])" <<<"$UP")
TASK_ID=$(python3 -c "import json,sys; print(json.load(sys.stdin).get('task_id') or '')" <<<"$UP")

if [[ -n "$TASK_ID" && "$TASK_ID" != "None" ]]; then
  echo "wait task $TASK_ID"
  for i in $(seq 1 120); do
    T=$(curl -sS "$API/api/v1/tasks/$TASK_ID")
    ST=$(python3 -c "import json,sys; print(json.load(sys.stdin)['status'])" <<<"$T")
    echo "  [$i] $ST"
    if [[ "$ST" == "done" || "$ST" == "failed" ]]; then
      break
    fi
    sleep 0.5
  done
  [[ "$ST" == "done" ]] || { echo "$T"; exit 1; }
fi

echo "stage $FILE_ID"
STG=$(curl -sS -X POST "$API/api/v1/intake/stage/$FILE_ID" \
  -H 'Content-Type: application/json' \
  -d '{"config_version":"v1","target_domain":"inventory"}')
echo "$STG" | python3 -c "import json,sys;d=json.load(sys.stdin);print({k:d.get(k) for k in ['status','version','clean_rows','fingerprint']});print('map', (d.get('dry_run') or {}).get('column_mapping'))"
VER=$(python3 -c "import json,sys; print(json.load(sys.stdin).get('version'))" <<<"$STG")
STATUS=$(python3 -c "import json,sys; print(json.load(sys.stdin).get('status'))" <<<"$STG")

if [[ "$STATUS" == "RELEASED" ]]; then
  echo "already RELEASED — restage after mapping fix requires API restart with new code; forcing re-stage by discard not allowed. Re-upload used new file_id above should be STAGED."
fi

if [[ "$STATUS" != "STAGED" ]]; then
  echo "unexpected staging status=$STATUS" >&2
  echo "$STG" | python3 -m json.tool
  exit 1
fi

echo "confirm version=$VER"
CONF=$(curl -sS -X POST "$API/api/v1/intake/stage/$FILE_ID/confirm" \
  -H "Content-Type: application/json" \
  -H "X-Ops-Token: $TOKEN" \
  -H "Idempotency-Key: republish-$(date +%s)" \
  -d "{\"version\": $VER, \"expected_status\": \"STAGED\"}")
echo "$CONF" | python3 -c "import json,sys;d=json.load(sys.stdin);print({k:d.get(k) for k in ['status','rows','target_table','idempotent']});print('release', (d.get('release') or {}).get('release_id'), 'clean', (d.get('release') or {}).get('clean_rows'))"

echo "ask"
ASK=$(curl -sS -X POST "$API/api/v1/ask" -H 'Content-Type: application/json' \
  -d '{"question":"库存表有多少行"}')
echo "$ASK" | python3 -c "import json,sys;d=json.load(sys.stdin);print({k:d.get(k) for k in ['ok','sql','rows','answer','error']}); print('SAMPLE_OK' if d.get('ok') and (d.get('data') or [{}])[0].get('row_count', d.get('rows')) not in (0,None) or (d.get('ok') and '0' not in str(d.get('answer',''))) else 'SAMPLE_CHECK')"
# clearer check via query
Q=$(curl -sS -X POST "$API/api/v1/query" -H 'Content-Type: application/json' -H "X-Ops-Token: $TOKEN" \
  -d '{"sql":"SELECT COUNT(*) AS c FROM fact_inventory"}')
echo "$Q" | python3 -c "import json,sys;d=json.load(sys.stdin);c=(d.get('data') or [{}])[0].get('c',0);print('fact_inventory_rows',c);print('SAMPLE_OK' if c and int(c)>0 else 'SAMPLE_CHECK')"
