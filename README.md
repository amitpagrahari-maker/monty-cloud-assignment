# 📸 Monty Cloud Assignment – Image Service

This project implements an **Instagram-like image upload service** using AWS Serverless components.  
It enables **image upload, retrieval, listing, searching, and deletion** operations with image metadata stored in DynamoDB.

---

## 🧱 Architecture Overview

### 🔧 AWS Components Used
| Component | Purpose |
|------------|----------|
| **API Gateway** | Exposes RESTful API endpoints |
| **AWS Lambda (Python 3.9)** | Implements CRUD business logic |
| **S3** | Stores the uploaded images |
| **DynamoDB** | Stores image metadata (id, file_name, created_at, etc.) |

All AWS services are **emulated locally using LocalStack** for full offline development.

---

## ⚙️ Local Development with LocalStack

### 🧩 1 Build Docker Image

Build all dependencies fresh and prepare your environment:

```bash
docker-compose build --no-cache
```

###  🧩 2 Start LocalStack in detached mode

```bash
docker-compose up -d
```

###  🧩 3 Check if the container is running

```bash
docker ps
```

###  🧩 3 Redeploy (Clean Setup)

```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

###  🧩 4 Setup AWS Services and Lambda Functions

```bash
docker exec -it localstack sh /app/setup-localstack.sh
```

###  🧩 5 Run all pytest test cases inside LocalStack

```bash
docker exec -it localstack pytest -v /app/tests/test_handler.py
```
