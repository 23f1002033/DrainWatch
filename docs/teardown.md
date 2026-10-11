# Teardown

Removes everything the backend created. Run from the repo root with the same
credentials used to deploy. Region ap-south-1, stack `drainwatch`.

1. Empty the evidence bucket. CloudFormation cannot delete a non-empty bucket.
   The bucket is not versioned, so a recursive delete is enough.

       BUCKET=$(aws cloudformation describe-stacks --stack-name drainwatch \
         --region ap-south-1 \
         --query "Stacks[0].Outputs[?OutputKey=='EvidenceBucketName'].OutputValue" \
         --output text)
       aws s3 rm "s3://$BUCKET" --recursive --region ap-south-1

2. Delete the stack. This removes the Lambda, HTTP API, DynamoDB table (with all
   incidents, events and members), the Cognito user pool and its users, the log
   group, the alarm, the optional SNS topic and the IAM role. Deletion protection
   is off on the user pool and the table so this works.

       cd infrastructure
       sam delete --stack-name drainwatch --region ap-south-1 --no-prompts

   `sam delete` also removes this stack's artifacts from the SAM managed bucket.

3. Optional: delete the SAM managed artifact stack if nothing else uses it. Empty
   its bucket first (it is versioned, so delete object versions too).

       aws cloudformation describe-stacks --stack-name aws-sam-cli-managed-default \
         --region ap-south-1 --query "Stacks[0].Outputs" --output table
       # empty the bucket shown, including versions, then:
       aws cloudformation delete-stack --stack-name aws-sam-cli-managed-default \
         --region ap-south-1

4. Delete the Amplify Hosting app (frontend). It is not part of the stack.

       aws amplify delete-app --app-id d2m9rrzhq9d5qo --region ap-south-1

5. Optional: delete the budget once billing has settled (a few days later).

       aws budgets delete-budget --account-id <ACCOUNT_ID> --budget-name drainwatch-5usd

6. Check that nothing is left.

       aws cloudformation list-stacks --region ap-south-1 \
         --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE DELETE_FAILED \
         --query "StackSummaries[].StackName"
       aws logs describe-log-groups --region ap-south-1 \
         --log-group-name-prefix /aws/lambda/drainwatch
       aws amplify list-apps --region ap-south-1 --query "apps[].name"
