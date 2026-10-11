#!/usr/bin/env bash
# Manual deploy of the Next.js static export (apps/web/out) to Amplify Hosting.
# Usage: scripts/deploy_web.sh   (build apps/web first)
set -euo pipefail
cd "$(dirname "$0")/.."
APP_ID=${AMPLIFY_APP_ID:-d2m9rrzhq9d5qo}
BRANCH=${AMPLIFY_BRANCH:-main}
export AWS_REGION=${AWS_REGION:-ap-south-1}
OUT=apps/web/out

[[ -f "$OUT/index.html" ]] || { echo "no $OUT/index.html; run the static export first" >&2; exit 1; }

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
(cd "$OUT" && zip -qr "$WORK/site.zip" . -x '.DS_Store' '*/.DS_Store')
echo "zip: $(du -h "$WORK/site.zip" | cut -f1), $(unzip -l "$WORK/site.zip" | tail -1 | awk '{print $2}') files"

read -r JOB_ID UPLOAD_URL < <(aws amplify create-deployment --app-id "$APP_ID" --branch-name "$BRANCH" \
  --query '[jobId,zipUploadUrl]' --output text)
echo "job: $JOB_ID"
curl -sf -X PUT -H 'Content-Type: application/zip' --upload-file "$WORK/site.zip" "$UPLOAD_URL" >/dev/null
aws amplify start-deployment --app-id "$APP_ID" --branch-name "$BRANCH" --job-id "$JOB_ID" \
  --query 'jobSummary.status' --output text

for _ in $(seq 1 60); do
  STATUS=$(aws amplify get-job --app-id "$APP_ID" --branch-name "$BRANCH" --job-id "$JOB_ID" \
    --query 'job.summary.status' --output text)
  case "$STATUS" in
    SUCCEED) echo "deployed: https://$BRANCH.$APP_ID.amplifyapp.com"; exit 0 ;;
    FAILED|CANCELLED) echo "deployment $STATUS" >&2; exit 1 ;;
  esac
  sleep 5
done
echo "timed out waiting; last status $STATUS" >&2
exit 1
