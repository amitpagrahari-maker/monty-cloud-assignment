import os
import json
import base64
import pytest
import boto3
from unittest.mock import patch
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from handler import upload_image, list_images, get_image, delete_image

# Set environment variables for LocalStack
os.environ["AWS_ACCESS_KEY_ID"] = "test"
os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

# Set default region for boto3
AWS_DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "http://localstack:4566")
DYNAMODB_ENDPOINT_URL = os.environ.get("DYNAMODB_ENDPOINT_URL", "http://localstack:4566")
BUCKET_NAME = os.getenv("BUCKET_NAME", "images-bucket")
TABLE_NAME = os.getenv("TABLE_NAME", "images-metadata")
s3 = boto3.client("s3", endpoint_url=S3_ENDPOINT_URL, region_name=AWS_DEFAULT_REGION, aws_access_key_id="test", aws_secret_access_key="test")
dynamodb = boto3.resource("dynamodb", endpoint_url=DYNAMODB_ENDPOINT_URL, region_name=AWS_DEFAULT_REGION, aws_access_key_id="test", aws_secret_access_key="test")

@pytest.fixture(scope="module", autouse=True)
def setup_localstack_resources():
    """Auto-inject AWS-like environment for tests."""
    os.environ["AWS_ACCESS_KEY_ID"] = "test"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    """Create S3 bucket and DynamoDB table once before tests."""
    # Create S3 bucket
    try:
        s3 = boto3.client("s3", endpoint_url=S3_ENDPOINT_URL, region_name=AWS_DEFAULT_REGION, aws_access_key_id="test", aws_secret_access_key="test")
        s3.create_bucket(Bucket=BUCKET_NAME)
    except s3.exceptions.BucketAlreadyOwnedByYou:
        pass
    dynamodb = boto3.resource("dynamodb", endpoint_url=DYNAMODB_ENDPOINT_URL, region_name=AWS_DEFAULT_REGION, aws_access_key_id="test", aws_secret_access_key="test")
    # Create DynamoDB table
    existing_tables = dynamodb.meta.client.list_tables()["TableNames"]
    if TABLE_NAME not in existing_tables:
        dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
    # Wait until table exists
    table = dynamodb.Table(TABLE_NAME)
    table.wait_until_exists()
# ------------------ SUCCESS CASES ------------------ #

def test_upload_image_success():
    """
    Test uploading an image successfully.
     1. Uploads a base64-encoded image.
     2. Asserts a 200 status code and presence of image ID in response.
     3. Validates the returned file name matches the uploaded one.
    """
    file_content = base64.b64encode(b"fake_image").decode()
    event = {
        "httpMethod": "POST",
        "body": json.dumps({"file_name": "test.png", "file_content": file_content})
    }
    resp = upload_image(event, None)
    print(resp)
    print(event)
    data = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert "id" in data
    assert data["file_name"] == "test.png"


def test_list_images_success():
    """
    Test listing images successfully.
     1. Uploads an image to ensure at least one exists.
     2. Calls list_images without filters.
     3. Asserts a 200 status code and that the returned list is non-empty
    """
    test_upload_image_success()
    resp = list_images({}, None)
    assert resp["statusCode"] == 200
    data = json.loads(resp["body"])
    assert len(data) > 0


def test_get_image_success():
    """
    Test retrieving an image successfully.
     1. Uploads an image and retrieves its ID.
     2. Calls get_image with the image ID.
     3. Asserts a 200 status code and that the returned metadata matches the uploaded image.
    """
    file_content = base64.b64encode(b"image123").decode()
    event_upload = {
        "httpMethod": "POST",
        "body": json.dumps({"file_name": "photo.jpg", "file_content": file_content})
    }
    resp_upload = upload_image(event_upload, None)
    upload_data = json.loads(resp_upload["body"])
    image_id = upload_data["id"]

    event_get = {"queryStringParameters": {"id": image_id}}
    resp_get = get_image(event_get, None)
    data_get = json.loads(resp_get["body"])

    assert resp_get["statusCode"] == 200
    assert data_get["id"] == image_id
    assert data_get["file_name"] == "photo.jpg"

def test_delete_image_success():
    """
    Test deleting an image successfully.
     1. Uploads an image and retrieves its ID.
     2. Calls delete_image with the image ID.
     3. Asserts a 200 status code indicating successful deletion.
    """
    file_content = base64.b64encode(b"delete_me").decode()
    event_upload = {
        "httpMethod": "POST",
        "body": json.dumps({"file_name": "del.png", "file_content": file_content})
    }
    resp_upload = upload_image(event_upload, None)
    upload_data = json.loads(resp_upload["body"])
    image_id = upload_data["id"]

    event_delete = {"httpMethod": "DELETE", "body": json.dumps({"id": image_id})}
    resp_delete = delete_image(event_delete, None)
    assert resp_delete["statusCode"] == 200

# ------------------ 4XX / USER ERROR CASES ------------------ #

def test_upload_invalid_method():
    """
    Test uploading an image with invalid HTTP method.
     1. Calls upload_image with GET instead of POST.
     2. Asserts a 405 status code indicating method not allowed."""
    event = {"httpMethod": "GET", "body": "{}"}
    resp = upload_image(event, None)
    assert resp["statusCode"] == 405


def test_upload_invalid_json():
    """
    Test uploading an image with invalid JSON body.
     1. Calls upload_image with malformed JSON.
     2. Asserts a 400 status code indicating bad request due to invalid JSON.
    """
    event = {"httpMethod": "POST", "body": "INVALID JSON"}
    resp = upload_image(event, None)
    assert resp["statusCode"] == 400


def test_delete_invalid_method():
    """
    Test deleting an image with invalid HTTP method.
     1. Calls delete_image with POST instead of DELETE.
     2. Asserts a 405 status code indicating method not allowed.
    """
    event = {"httpMethod": "POST", "body": "{}"}
    resp = delete_image(event, None)
    assert resp["statusCode"] == 405


def test_delete_missing_id():
    """
    Test deleting an image with missing ID in body.
     1. Calls delete_image with empty body.
     2. Asserts a 400 status code indicating bad request due to missing ID.
    """
    event = {"httpMethod": "DELETE", "body": json.dumps({})}
    resp = delete_image(event, None)
    assert resp["statusCode"] == 400


def test_get_image_missing_id():
    """
    Test retrieving an image with missing ID parameter.
     1. Calls get_image without the 'id' query parameter.
     2. Asserts a 400 status code indicating bad request due to missing ID.
    """
    event = {"queryStringParameters": {"wrong_key": "123"}}
    resp = get_image(event, None)
    assert resp["statusCode"] == 400

# ------------------ 5XX / SYSTEM ERROR CASES ------------------ #

def test_s3_failure():
    """
    Test uploading an image when S3 upload fails.
     1. Mocks S3 put_object to raise an exception.
     2. Calls upload_image and asserts a 500 status code indicating server error.
    """
    with patch("handler.s3.put_object", side_effect=Exception("S3 failed")):
        file_content = base64.b64encode(b"data").decode()
        event = {"httpMethod": "POST", "body": json.dumps({"file_name": "fail.png", "file_content": file_content})}
        resp = upload_image(event, None)
        assert resp["statusCode"] == 500


def test_dynamodb_failure():
    """
    Test uploading an image when DynamoDB put_item fails.
     1. Mocks DynamoDB Table put_item to raise an exception.
     2. Calls upload_image and asserts a 500 status code indicating server error.
    """
    with patch("handler.dynamodb.Table") as mock_table:
        mock_table.return_value.put_item.side_effect = Exception("DynamoDB failed")
        file_content = base64.b64encode(b"data").decode()
        event = {"httpMethod": "POST", "body": json.dumps({"file_name": "fail2.png", "file_content": file_content})}
        resp = upload_image(event, None)
        assert resp["statusCode"] == 500


def test_list_images_failure():
    """
    Test listing images when DynamoDB scan fails.
     1. Mocks DynamoDB Table scan to raise an exception.
     2. Calls list_images and asserts a 500 status code indicating server error.
    """
    with patch("handler.dynamodb.Table") as mock_table:
        mock_table.return_value.scan.side_effect = Exception("Scan failed")
        resp = list_images({}, None)
        assert resp["statusCode"] == 500


# ------------------ EDGE CASES ------------------ #

def test_double_delete():
    """
    Test deleting an image twice.
     1. Uploads an image and retrieves its ID.
     2. Deletes the image once successfully.
     3. Attempts to delete the same image again and asserts a 404 status code indicating not found.
    """
    file_content = base64.b64encode(b"delete_twice").decode()
    event_upload = {"httpMethod": "POST", "body": json.dumps({"file_name": "dup.png", "file_content": file_content})}
    resp_upload = upload_image(event_upload, None)
    image_id = json.loads(resp_upload["body"])["id"]

    event_delete = {"httpMethod": "DELETE", "body": json.dumps({"id": image_id})}
    delete_image(event_delete, None)  # first delete
    resp2 = delete_image(event_delete, None)  # second delete
    assert resp2["statusCode"] == 404


def test_large_file_upload():
    """
    Test uploading a very large image file.
     1. Creates a large base64-encoded string (e.g., 5MB).
     2. Calls upload_image with the large file content.
     3. Asserts either a 200 status code (if handled) or a 500 status code (if it fails due to size).
    """
    big_data = base64.b64encode(b"x" * (5 * 1024 * 1024)).decode()  # 5MB
    event = {"httpMethod": "POST", "body": json.dumps({"file_name": "big.bin", "file_content": big_data})}
    resp = upload_image(event, None)
    assert resp["statusCode"] in (200, 500)  # depending on limits
