import sys
import os
sys.path.insert(0, os.path.abspath("."))
import asyncio
import httpx
from sqlalchemy import select
from app.core.retry import is_retryable, retry_call
from app.core.dlq import scrub_payload, write_to_dlq
from app.core.database import AsyncSessionLocal
from app.models.dlq import FailedExternalCall

async def test_resilience_and_dlq():
    print("Testing Resilience & DLQ...")

    # 1. is_retryable checks
    timeout_exc = httpx.TimeoutException("Connection timed out")
    assert is_retryable(timeout_exc) is True

    req = httpx.Request("POST", "http://example.com")
    resp_503 = httpx.Response(503, request=req)
    http_503 = httpx.HTTPStatusError("503 Service Unavailable", request=req, response=resp_503)
    assert is_retryable(http_503) is True

    resp_400 = httpx.Response(400, request=req)
    http_400 = httpx.HTTPStatusError("400 Bad Request", request=req, response=resp_400)
    assert is_retryable(http_400) is False

    value_err = ValueError("Invalid input")
    assert is_retryable(value_err) is False
    print("  [PASS] is_retryable classification")

    # 2. retry_call transient recovery
    call_count = 0
    async def flaky_fn():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.ConnectError("Temporary glitch")
        return "success"

    res = await retry_call(flaky_fn, max_retries=3, delays=[0.05, 0.05, 0.05], op_label="test_flaky")
    assert res == "success"
    assert call_count == 3
    print("  [PASS] retry_call recovered after transient retries")

    # 3. scrub_payload test
    sensitive_data = {
        "client_id": "my_client_id",
        "client_secret": "SUPER_SECRET_VALUE",
        "password": "my_password",
        "nested": {
            "access_token": "bearer_xyz",
            "normal_field": "hello"
        }
    }
    scrubbed = scrub_payload(sensitive_data)
    assert scrubbed["client_secret"] == "[REDACTED]"
    assert scrubbed["password"] == "[REDACTED]"
    assert scrubbed["nested"]["access_token"] == "[REDACTED]"
    assert scrubbed["nested"]["normal_field"] == "hello"
    print("  [PASS] scrub_payload sensitive data redaction")

    # 4. write_to_dlq persistence test
    test_scan_id = "test_dlq_scan_001"
    await write_to_dlq(
        target_service="salesforce",
        operation="create_query_job",
        payload=sensitive_data,
        attempts=3,
        error=Exception("Salesforce Bulk API 500 error"),
        organization_id="org_test_123",
        scan_id=test_scan_id
    )

    async with AsyncSessionLocal() as session:
        stmt = select(FailedExternalCall).where(FailedExternalCall.scan_id == test_scan_id)
        result = await session.execute(stmt)
        record = result.scalars().first()
        assert record is not None
        assert record.target_service == "salesforce"
        assert record.payload["client_secret"] == "[REDACTED]"
        assert record.payload["password"] == "[REDACTED]"
        assert "500 error" in record.last_error
        # Clean up test row
        await session.delete(record)
        await session.commit()

    print("  [PASS] write_to_dlq verified in PostgreSQL")
    print("\nALL RESILIENCE & DLQ TESTS PASSED SUCCESSFULLY!\n")

if __name__ == "__main__":
    asyncio.run(test_resilience_and_dlq())
