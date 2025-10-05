#!/bin/sh
set -e

export AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-test}
export AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-test}
export AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}

echo "⏳ Waiting for LocalStack services..."
until curl -s http://localhost:4566/_localstack/health | grep -q '"available"'; do
    echo "Waiting for LocalStack..."
    sleep 3
done
echo "✅ LocalStack ready."

AWSCLI="awslocal"

# -----------------------------
# 1️⃣ Create S3 bucket
# -----------------------------
echo "Creating S3 bucket..."
$AWSCLI s3 mb s3://images-bucket

# -----------------------------
# 2️⃣ Create DynamoDB table
# -----------------------------
echo "Creating DynamoDB table..."
$AWSCLI dynamodb create-table \
    --table-name images-metadata \
    --attribute-definitions AttributeName=id,AttributeType=S \
    --key-schema AttributeName=id,KeyType=HASH \
    --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5

# -----------------------------
# 3️⃣ Create IAM role
# -----------------------------
ROLE_NAME="IamRoleForLambda"
TRUST_POLICY='{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "lambda.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}'

echo "Creating IAM role..."
ROLE_ARN=$($AWSCLI iam create-role \
    --role-name $ROLE_NAME \
    --assume-role-policy-document "$TRUST_POLICY" \
    --query 'Role.Arn' --output text)
echo "✅ IAM role created: $ROLE_ARN"

# -----------------------------
# 4️⃣ Create Lambda functions
# -----------------------------
lambda_functions="upload_image list_images get_image delete_image"

for func in $lambda_functions; do
    echo "Creating Lambda function $func..."
    zip -j /tmp/${func}.zip /app/handler.py

    # Create Lambda
    set +e
    $AWSCLI lambda create-function \
        --function-name ${func} \
        --runtime python3.7 \
        --handler handler.${func} \
        --zip-file fileb:///tmp/${func}.zip \
        --role $ROLE_ARN \
        --timeout 30
    status=$?
    set -e

    if [ "$status" -eq 0 ]; then
        echo "⏳ Waiting for Lambda $func to become active..."
        $AWSCLI lambda wait function-active-v2 --function-name $func
        echo "✅ Lambda $func is active."
    else
        echo "❌ Failed to create Lambda $func. Check logs."
        exit 1
    fi
done

# -----------------------------
# 5️⃣ Create REST API
# -----------------------------
echo "Creating REST API..."
API_ID=$($AWSCLI apigateway create-rest-api --name ImageService --query 'id' --output text)
echo "✅ REST API created: $API_ID"

# Wait until root resource is available
RETRIES=10
i=0
PARENT_ID=""
while [ "$i" -lt "$RETRIES" ]; do
    PARENT_ID=$($AWSCLI apigateway get-resources --rest-api-id $API_ID --query 'items[?path==`/`].id' --output text)
    if [ -n "$PARENT_ID" ]; then
        break
    fi
    echo "Waiting for root resource..."
    sleep 2
    i=$((i+1))
done

# -----------------------------
# 6️⃣ Create resources, methods, integrations
# -----------------------------
routes="upload list get delete"
methods="POST GET GET DELETE"

i=1
for path in $routes; do
    method=$(echo $methods | cut -d' ' -f$i)
    case $path in
        upload) func="upload_image" ;;
        list) func="list_images" ;;
        get) func="get_image" ;;
        delete) func="delete_image" ;;
    esac

    echo "Creating API resource $path ($method)..."
    RESOURCE_ID=$($AWSCLI apigateway create-resource \
        --rest-api-id $API_ID \
        --parent-id $PARENT_ID \
        --path-part $path \
        --query 'id' --output text)

    $AWSCLI apigateway put-method \
        --rest-api-id $API_ID \
        --resource-id $RESOURCE_ID \
        --http-method $method \
        --authorization-type NONE

    $AWSCLI apigateway put-integration \
        --rest-api-id $API_ID \
        --resource-id $RESOURCE_ID \
        --http-method $method \
        --type AWS_PROXY \
        --integration-http-method POST \
        --uri arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/arn:aws:lambda:us-east-1:000000000000:function:$func/invocations

    i=$((i+1))
done

# -----------------------------
# 7️⃣ Deploy API
# -----------------------------
$AWSCLI apigateway create-deployment --rest-api-id $API_ID --stage-name local
echo "✅ REST API deployed!"

# Print endpoints
i=1
for path in $routes; do
    method=$(echo $methods | cut -d' ' -f$i)
    echo "$method http://localhost:4566/restapis/$API_ID/local/_user_request_/$path"
    i=$((i+1))
done

echo "🎉 LocalStack REST API setup complete!"
