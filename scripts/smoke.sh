#!/usr/bin/env bash
# Smoke test against the deployed stack. Needs AWS credentials, the DW_PW_* env vars used
# by seed_demo.py, and optionally SMOKE_PHOTO=/path/to/photo.jpg. Never prints tokens.
set -euo pipefail
cd "$(dirname "$0")/.."
STACK=${DW_STACK:-drainwatch}
export AWS_REGION=${AWS_REGION:-ap-south-1}
DOMAIN=${DW_EMAIL_DOMAIN:-example.com}
PY=(uv run --quiet --project services/api python)

out() { aws cloudformation describe-stacks --stack-name "$STACK" --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
API=$(out ApiUrl)/api/v1
POOL=$(out UserPoolId)
CLIENT=$(out AppClientId)
echo "API=$API"

token() { "${PY[@]}" scripts/get_token.py "$1@$DOMAIN" "$2" "$POOL" "$CLIENT"; }
OP=$(token op-demo DW_PW_OP_DEMO)
RAVI=$(token fw-ravi DW_PW_FW_RAVI)
MEENA=$(token fw-meena DW_PW_FW_MEENA)
OTHER=$(token op-other DW_PW_OP_OTHER)
echo "tokens: 4 ID tokens fetched via admin-initiate-auth (not shown)"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
PHOTO=${SMOKE_PHOTO:-}
if [[ -z "$PHOTO" ]]; then
  PHOTO="$WORK/photo.jpg"
  sips -s format jpeg -Z 1600 "/System/Library/Desktop Pictures/Hello Metallic Orange.heic" \
    --out "$PHOTO" >/dev/null
fi
echo "photo: $(basename "$PHOTO") $(wc -c <"$PHOTO" | tr -d ' ') bytes, $(file -b --mime-type "$PHOTO")"

pass=0; fail=0
check() { # name expected actual
  if [[ "$2" == "$3" ]]; then pass=$((pass+1)); echo "PASS $1 -> $3";
  else fail=$((fail+1)); echo "FAIL $1 -> got $3, want $2"; head -c 300 "$WORK/body" 2>/dev/null | sed 's/^/     body: /'; echo; fi
}
req() { # method url token [json]
  local args=(-s -o "$WORK/body" -w '%{http_code}' -X "$1" "$2")
  [[ -n "$3" ]] && args+=(-H "Authorization: Bearer $3")
  [[ $# -ge 4 ]] && args+=(-H 'Content-Type: application/json' -d "$4")
  curl "${args[@]}"
}
body() { cat "$WORK/body"; }
jq_() { "${PY[@]}" -c "import json,sys; d=json.load(open('$WORK/body')); print($1)"; }

# CORS preflight as a browser sends it. Must be 2xx, echo the origin and allow our headers.
# Regression guard: an ANY route sends OPTIONS to the JWT authorizer and answers 401.
ORIGINS=${SMOKE_ORIGINS:-"https://main.d2m9rrzhq9d5qo.amplifyapp.com http://localhost:3000"}
REQ_HEADERS="authorization,content-type,idempotency-key"
preflight() { # path method origin -> "status|allow-origin|allow-headers"
  curl -s -o /dev/null -D - -X OPTIONS "$API$1" -H "Origin: $3" \
    -H "Access-Control-Request-Method: $2" -H "Access-Control-Request-Headers: $REQ_HEADERS" \
    | tr -d '\r' | awk -F': ' '
      /^HTTP/ {s=$2; split($0, a, " "); s=a[2]}
      tolower($1)=="access-control-allow-origin" {o=$2}
      tolower($1)=="access-control-allow-headers" {h=tolower($2)}
      END {print s "|" o "|" h}'
}
for origin in $ORIGINS; do
  for route in "GET /incidents" "POST /incidents/01J00000000000000000000000/transitions" \
               "POST /public/demo-campus/incidents"; do
    IFS='|' read -r st ao ah <<<"$(preflight "/api/v1${route#* }" "${route%% *}" "$origin")"
    ok=yes
    [[ "$st" == 2?? ]] || ok="status $st"
    [[ "$ao" == "$origin" ]] || ok="allow-origin '$ao'"
    for h in ${REQ_HEADERS//,/ }; do [[ ",$ah," == *",$h,"* ]] || ok="missing allow-header $h"; done
    check "preflight $route from $origin" yes "$ok"
  done
done
IFS='|' read -r st ao ah <<<"$(preflight /api/v1/incidents GET https://evil.example.com)"
check "preflight from other origin gets no allow-origin" "" "$ao"

KEY="smoke-$(date +%s)"
REPORT='{"type":"blocked_drain","description":"Smoke test: drain blocked near main gate","landmark":"Main gate"}'
code=$(curl -s -o "$WORK/body" -w '%{http_code}' -X POST "$API/public/demo-campus/incidents" \
  -H 'Content-Type: application/json' -H "Idempotency-Key: $KEY" -d "$REPORT")
check "public report" 201 "$code"; REF=$(jq_ 'd["reference"]'); echo "     reference=$REF"
code=$(curl -s -o "$WORK/body" -w '%{http_code}' -X POST "$API/public/demo-campus/incidents" \
  -H 'Content-Type: application/json' -H "Idempotency-Key: $KEY" -d "$REPORT")
check "idempotent retry same reference" "$REF" "$(jq_ 'd["reference"]')"

check "no token -> 401" 401 "$(req GET "$API/incidents" "")"
check "operator queue" 200 "$(req GET "$API/incidents?status=reported&limit=100" "$OP")"
ID=$(jq_ "[i['id'] for i in d['items'] if i['reference']=='$REF'][0]")
echo "     incident=$ID"

check "other-campus operator GET -> 404" 404 "$(req GET "$API/incidents/$ID" "$OTHER")"
check "other-campus events -> 404" 404 "$(req GET "$API/incidents/$ID/events" "$OTHER")"
req GET "$API/incidents" "$OTHER" >/dev/null
check "other-campus queue excludes it" False "$(jq_ "any(i['id']=='$ID' for i in d['items'])")"

check "field worker triage -> 403" 403 \
  "$(req POST "$API/incidents/$ID/triage" "$RAVI" '{"severity":"S1","reason":"x","expected_version":1}')"
check "triage S2" 200 \
  "$(req POST "$API/incidents/$ID/triage" "$OP" '{"severity":"S2","reason":"ponding at gate","expected_version":1}')"

check "workers (MEMBER items)" 200 "$(req GET "$API/workers" "$OP")"
jq_ "'     ' + ', '.join(w['name'] for w in d['items'])"
RAVI_SUB=$(jq_ "[w['id'] for w in d['items'] if w['name']=='Ravi'][0]")
# bash 3.2 brace-expands "{..,..}" inside "$(...)", so JSON bodies go through a variable.
P=$(printf '{"worker_id":"%s","reason":"nearest","expected_version":2}' "$RAVI_SUB")
check "assign Ravi" 200 "$(req POST "$API/incidents/$ID/assignments" "$OP" "$P")"
check "Meena (not assignee) start -> 403" 403 \
  "$(req POST "$API/incidents/$ID/transitions" "$MEENA" '{"to":"in_progress","expected_version":3}')"
check "stale version -> 409" 409 \
  "$(req POST "$API/incidents/$ID/transitions" "$RAVI" '{"to":"in_progress","expected_version":2}')"
check "Ravi start" 200 \
  "$(req POST "$API/incidents/$ID/transitions" "$RAVI" '{"to":"in_progress","expected_version":3}')"

check "presign POST" 201 \
  "$(req POST "$API/incidents/$ID/uploads" "$RAVI" '{"content_type":"image/jpeg"}')"
cp "$WORK/body" "$WORK/signed.json"
S3URL=$("${PY[@]}" -c "import json; print(json.load(open('$WORK/signed.json'))['url'])")
S3KEY=$("${PY[@]}" -c "import json; print(json.load(open('$WORK/signed.json'))['key'])")
form() { "${PY[@]}" -c "import json; [print(f'-F\n{k}={v}') for k,v in json.load(open('$WORK/signed.json'))['fields'].items()]"; }
FIELDS=(); while IFS= read -r l; do FIELDS+=("$l"); done < <(form)
echo "     upload url host: $(echo "$S3URL" | cut -d/ -f3)"

EVID=$(printf '{"key":"%s","kind":"before"}' "$S3KEY")
check "evidence before upload -> 422" 422 "$(req POST "$API/incidents/$ID/evidence" "$RAVI" "$EVID")"
head -c $((5*1024*1024+1)) /dev/zero > "$WORK/big.jpg"
code=$(curl -s -o "$WORK/s3err" -w '%{http_code}' "$S3URL" "${FIELDS[@]}" -F "file=@$WORK/big.jpg;type=image/jpeg")
check "S3 rejects 5MB+1 upload" 400 "$code"; grep -o '<Code>[^<]*' "$WORK/s3err" | sed 's/<Code>/     s3: /' || true
WRONG=()
for f in "${FIELDS[@]}"; do [[ "$f" == Content-Type=* ]] && WRONG+=("Content-Type=image/png") || WRONG+=("$f"); done
code=$(curl -s -o "$WORK/s3err" -w '%{http_code}' "$S3URL" "${WRONG[@]}" -F "file=@$PHOTO;type=image/png")
check "S3 rejects changed Content-Type" 403 "$code"; grep -o '<Code>[^<]*' "$WORK/s3err" | sed 's/<Code>/     s3: /' || true
code=$(curl -s -o "$WORK/s3err" -w '%{http_code}' "$S3URL" "${FIELDS[@]}" -F "file=@$PHOTO;type=image/jpeg")
check "S3 accepts real photo" 204 "$code"
check "register before evidence" 200 "$(req POST "$API/incidents/$ID/evidence" "$RAVI" "$EVID")"
aws s3api head-object --bucket "$(out EvidenceBucketName)" --key "$S3KEY" \
  --query '{size:ContentLength,type:ContentType,sse:ServerSideEncryption}' --output text | sed 's/^/     head: /'
check "public GET of object -> 403" 403 \
  "$(curl -s -o /dev/null -w '%{http_code}' "${S3URL%/}/$S3KEY")"

check "detail with evidence URL" 200 "$(req GET "$API/incidents/$ID" "$RAVI")"
PHOTO_URL=$(jq_ "d['evidence'][0]['url']")
check "evidence URL expires in 300 s" 300 "$(jq_ "d['evidence'][0]['url_expires_in']")"
code=$(curl -s -o "$WORK/download" -w '%{http_code} %{content_type}' "$PHOTO_URL")
check "fetch presigned photo URL" "200 image/jpeg" "$code"
check "downloaded bytes match upload" "$(wc -c <"$PHOTO" | tr -d ' ')" \
  "$(wc -c <"$WORK/download" | tr -d ' ')"
check "other-campus detail -> 404" 404 "$(req GET "$API/incidents/$ID" "$OTHER")"
check "members as field worker" 200 "$(req GET "$API/members" "$MEENA")"
jq_ "'     ' + ', '.join(m['name'] + ' (' + m['role'] + ')' for m in d['items'])"
req GET "$API/incidents/$ID" "$RAVI" >/dev/null
V=$(jq_ 'd["version"]')
P=$(printf '{"to":"resolved","note":"cleared silt","expected_version":%s}' "$V")
check "resolve" 200 "$(req POST "$API/incidents/$ID/transitions" "$RAVI" "$P")"
V=$(jq_ 'd["version"]')
P=$(printf '{"to":"closed","expected_version":%s}' "$V")
check "close" 200 "$(req POST "$API/incidents/$ID/transitions" "$OP" "$P")"
check "events" 200 "$(req GET "$API/incidents/$ID/events" "$OP")"
jq_ "'\n'.join(f\"     {e['action']:<14} {e['actor_role']:<12} v{e['after']['version']}\" for e in d['items'])"

echo "summary: $pass passed, $fail failed"
[[ $fail -eq 0 ]]
