# Cost: DrainWatch backend, ap-south-1 (Mumbai)

Prices are the AWS public Price List for ap-south-1, fetched 2026-10-11
(`pricing.us-east-1.amazonaws.com/offers/v1.0/aws/<Service>/current/ap-south-1/index.json`).
Budgets, Cost Explorer and Cognito tier rules come from the AWS pricing pages.
The estimate ignores free-tier allowances except where the price list itself
prices the first units at $0 (DynamoDB storage, Cognito MAU).

## Pilot assumptions (1 week)

2 tenants, 4 staff users, about 30 public reports, 10,000 API requests in all
(staff polling the queue), 100 photos of about 2 MB, warm Lambda about 150 ms.

## Resources

| Resource | Pricing basis (ap-south-1) | 1-week pilot |
|---|---|---|
| Lambda, arm64, 512 MB | $0.20 per 1M requests; $0.0000133334 per GB-second | $0.012 |
| API Gateway HTTP API | $1.05 per 1M requests (first 300M) | $0.011 |
| JWT authorizer | included in HTTP API request price | $0 |
| DynamoDB on-demand | $0.1425 per 1M RRU; $0.71 per 1M WRU (transactional writes cost 2x); storage first 25 GB-month $0 | $0.015 |
| DynamoDB TTL deletes | free | $0 |
| DynamoDB PITR | disabled | $0 |
| S3 Standard, SSE-S3 | $0.025 per GB-month; $0.005 per 1,000 PUT/POST; $0.0004 per 1,000 GET/HEAD; SSE-S3 has no charge | $0.003 |
| Cognito user pool, Lite tier | 10,000 MAU free per account, then $0.0055 per MAU. Essentials ($0.015 per MAU) is the default for new pools, so the template sets `UserPoolTier: LITE` | $0 |
| CloudWatch Logs | $0.67 per GB ingested; $0.03 per GB-month stored; 14-day retention | $0.007 |
| CloudWatch alarms (2, standard: Lambda Errors, HTTP API 5xx) | $0.10 per alarm-month, prorated | $0.047 |
| SNS email for the alarm (optional) | first 1,000 email deliveries per month free | $0 |
| AWS Budget ($5, email alert) | budgets without actions are free; only action-enabled budgets past the first two cost $0.10/day | $0 |
| Cost Explorer API | $0.01 per request. Console views are not billed per request | $0.01 (one query) |
| CloudFormation / SAM | no charge for AWS:: resource types | $0 |
| SAM artifact bucket | S3 Standard, about 10 MB of zips | < $0.001 |
| Data transfer out | first 100 GB/month to internet free account-wide | $0 |
| KMS | not used (SSE-S3, DynamoDB AWS-owned key) | $0 |

Expected total: about $0.10 for the week. At 10x the traffic it is about
$0.53. Both are well under the $2 target. The fixed part is the two alarms.
HTTP API basic metrics (4xx, 5xx, Count, Latency) are free; detailed per-route
metrics are not enabled.

## What could make it cost more

- A client loop hammering the API. The stage throttle (20 rps, burst 40) caps it
  at 72,000 requests per hour, about $0.16 per hour for HTTP API plus Lambda.
- Public spam reports. Capped at 2 rps (burst 5) on the public route.
- Photos: max 5 MB each by POST policy. 1,000 photos is still about $0.13 per month.
- Lambda errors are logged without bodies, so log volume stays small.

## Budget alert

`drainwatch-5usd`, created 2026-10-11 before the first deploy: email at actual
spend > 50% ($2.50) and forecast > 100% ($5). A budget is a delayed alert, not a cap: AWS
refreshes billing data up to 3 times a day.

    aws budgets create-budget --account-id <ACCOUNT_ID> \
      --budget '{"BudgetName":"drainwatch-5usd","BudgetLimit":{"Amount":"5","Unit":"USD"},
                 "TimeUnit":"MONTHLY","BudgetType":"COST"}' \
      --notifications-with-subscribers '[
        {"Notification":{"NotificationType":"ACTUAL","ComparisonOperator":"GREATER_THAN",
                         "Threshold":50,"ThresholdType":"PERCENTAGE"},
         "Subscribers":[{"SubscriptionType":"EMAIL","Address":"<EMAIL>"}]},
        {"Notification":{"NotificationType":"FORECASTED","ComparisonOperator":"GREATER_THAN",
                         "Threshold":100,"ThresholdType":"PERCENTAGE"},
         "Subscribers":[{"SubscriptionType":"EMAIL","Address":"<EMAIL>"}]}]'
