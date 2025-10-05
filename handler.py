import json
import base64
import boto3
import os
import uuid
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr
from datetime import datetime

# Environment variables and AWS clients
AWS_DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
DYNAMODB_ENDPOINT_URL = os.environ.get("DYNAMODB_ENDPOINT_URL", "http://localstack:4566")
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "http://localstack:4566")
# AWS clients for LocalStack
s3 = boto3.client("s3", endpoint_url=S3_ENDPOINT_URL, region_name=AWS_DEFAULT_REGION)
dynamodb = boto3.resource("dynamodb", endpoint_url=DYNAMODB_ENDPOINT_URL, region_name=AWS_DEFAULT_REGION)

BUCKET_NAME = os.getenv("BUCKET_NAME", "images-bucket")
TABLE_NAME = os.getenv("TABLE_NAME", "images-metadata")


# ------------------------- Helpers ------------------------- #
def response(status_code, body_dict):
    """
    Ensure consistent JSON string responses.
    """
    return {"statusCode": status_code, "body": json.dumps(body_dict)}


# ------------------------- Lambda Handlers ------------------------- #
def upload_image(event, context):
    """
    Upload an image to S3 and store metadata in DynamoDB.
    Expected JSON body:
    {
        "file_name": "example.png",
        "file_content": "<base64-encoded-content>",
        "metadata": {"key1": "value1", ...}  # optional
    }
    Returns the unique ID assigned to the image.
    1. Validates input and decodes base64 content.
    2. Uploads image to S3 bucket.
    3. Stores metadata in DynamoDB with a unique ID.
    4. Returns success message with image ID.
    5. If any error occurs, returns a 500 error.
    """
    try:
        if event.get("httpMethod") != "POST":
            return response(405, {"error": "Method not allowed, use POST"})

        body_str = event.get("body")
        if not body_str:
            return response(400, {"error": "Request body is missing"})

        try:
            body = json.loads(body_str)
        except json.JSONDecodeError:
            return response(400, {"error": "Invalid JSON in body"})

        file_name = body.get("file_name")
        file_content_b64 = body.get("file_content")
        metadata = body.get("metadata", {})

        if not file_name or not file_content_b64:
            return response(400, {"error": "file_name and file_content required"})

        try:
            file_content = base64.b64decode(file_content_b64)
        except Exception:
            return response(400, {"error": "Invalid base64 for file_content"})

        # Generate unique ID
        unique_id = str(uuid.uuid4())

        # Upload to S3
        s3.put_object(Bucket=BUCKET_NAME, Key=file_name, Body=file_content)
        created_at = datetime.now().date().isoformat()
        # Store metadata in DynamoDB
        table = dynamodb.Table(TABLE_NAME)
        table.put_item(Item={"id": unique_id, "file_name": file_name, "metadata": metadata, "created_at": created_at})

        return response(200, {"message": "Image uploaded", "file_name": file_name, "id": unique_id})

    except Exception as e:
        return response(500, {"error": str(e)})


def list_images(event, context):
    """
    List images with optional search filters: file_name and created_at.
    Example query parameters:
        ?file_name=test.png
        ?created_at=2025-10-05
    Returns a list of image metadata.
    1. If no filters are provided, returns all images.
    2. If filters are provided, returns images matching all filters.
    3. If any error occurs, returns a 500 error.
    """
    try:
        params = event.get("queryStringParameters", {}) or {}
        file_name_filter = params.get("file_name")
        created_at_filter = params.get("created_at")

        table = dynamodb.Table(TABLE_NAME)

        filter_expr = None
        if file_name_filter:
            filter_expr = Attr("file_name").eq(file_name_filter)
        if created_at_filter:
            expr = Attr("created_at").eq(created_at_filter)
            filter_expr = expr if filter_expr is None else filter_expr & expr

        if filter_expr:
            response_items = table.scan(FilterExpression=filter_expr).get("Items", [])
        else:
            response_items = table.scan().get("Items", [])

        return response(200, {"images": response_items})

    except Exception as e:
        return response(500, {"error": str(e)})

def get_image(event, context):
    """
    Retrieve an image and its metadata by ID.
    Expected query parameter: ?id=<image_id>
    Returns the image file content (base64-encoded) and metadata.
    1. Fetches metadata from DynamoDB using the provided ID.
    2. If the metadata does not exist, returns a 404 error.
    3. Fetches the image file from S3 using the file_name from metadata.
    4. If the image file does not exist in S3, returns a 404 error.
    5. Returns the image file content (base64-encoded) and metadata.
    6. If the id parameter is missing, returns a 400 error.
    7. If any other error occurs, returns a 500 error.
    """
    try:
        params = event.get("queryStringParameters", {})
        image_id = params.get("id")

        if not image_id:
            return response(400, {"error": "Missing id in query parameters"})

        table = dynamodb.Table(TABLE_NAME)
        result = table.get_item(Key={"id": image_id})
        item = result.get("Item")
        if not item:
            return response(404, {"error": "Image not found"})

        file_name = item["file_name"]
        created_at = item.get("created_at", "")
        s3_obj = s3.get_object(Bucket=BUCKET_NAME, Key=file_name)
        file_content_b64 = base64.b64encode(s3_obj["Body"].read()).decode()

        return response(200, {"id": image_id, "file_name": file_name, "file_content": file_content_b64, "created_at": created_at})

    except ClientError as e:
        return response(404, {"error": str(e)})
    except Exception as e:
        return response(500, {"error": str(e)})


def delete_image(event, context):
    """
    Delete an image by ID.
    Expected JSON body:
    {
        "id": "<image_id>"
    }
    1. Deletes the image from S3.
    2. Deletes the metadata from DynamoDB.
    3. Returns success message.
    4. If the image does not exist, returns 404 error.
    5. If the request method is not DELETE, returns 405 error.
    6. If the request body is missing or invalid, returns 400 error.
    7. If any other error occurs, returns 500 error.
    8. If the image is already deleted, returns 404 error.
    """
    try:
        if event.get("httpMethod") != "DELETE":
            return response(405, {"error": "Method not allowed, use DELETE"})

        body_str = event.get("body")
        if not body_str:
            return response(400, {"error": "Request body missing"})

        try:
            body = json.loads(body_str)
        except json.JSONDecodeError:
            return response(400, {"error": "Invalid JSON in body"})

        image_id = body.get("id")
        if not image_id:
            return response(400, {"error": "Missing id in body"})

        table = dynamodb.Table(TABLE_NAME)
        result = table.get_item(Key={"id": image_id})
        item = result.get("Item")
        if not item:
            return response(404, {"error": "Image not found"})

        file_name = item["file_name"]
        s3.delete_object(Bucket=BUCKET_NAME, Key=file_name)
        table.delete_item(Key={"id": image_id})

        return response(200, {"message": "Deleted successfully", "id": image_id})

    except ClientError as e:
        return response(404, {"error": str(e)})
    except Exception as e:
        return response(500, {"error": str(e)})
