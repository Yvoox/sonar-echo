"""MinIO/S3 storage helper."""
import io
import uuid

from app.config import settings
from app.db.minio import ensure_bucket, get_client


def upload_bytes(data: bytes, key: str, content_type: str) -> str:
    ensure_bucket()
    client = get_client()
    client.put_object(
        bucket_name=settings.minio_bucket,
        object_name=key,
        data=io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return f"s3://{settings.minio_bucket}/{key}"


def download_bytes(uri: str) -> bytes:
    # uri = s3://bucket/key
    if not uri.startswith("s3://"):
        raise ValueError(f"unsupported uri: {uri}")
    rest = uri[len("s3://"):]
    bucket, key = rest.split("/", 1)
    client = get_client()
    resp = client.get_object(bucket, key)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()


def delete_object(uri: str) -> None:
    if not uri.startswith("s3://"):
        return
    rest = uri[len("s3://"):]
    bucket, key = rest.split("/", 1)
    client = get_client()
    client.remove_object(bucket, key)


def make_key(kb_id: uuid.UUID, doc_id: uuid.UUID, filename: str) -> str:
    safe = filename.replace("/", "_")
    return f"kb/{kb_id}/docs/{doc_id}/{safe}"
