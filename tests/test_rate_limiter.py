import asyncio
import time
import pytest
from starlette.requests import Request
from place.rate_limiter import SlidingWindowRateLimiter, extract_client_ip


def make_mock_request(headers: dict[str, str] | None = None, client_host: str = "127.0.0.1") -> Request:
    scope = {
        "type": "http",
        "headers": [(k.lower().encode("latin1"), v.encode("latin1")) for k, v in (headers or {}).items()],
        "client": (client_host, 12345),
    }
    return Request(scope)


def test_extract_client_ip() -> None:
    # Direct client
    req = make_mock_request(client_host="192.168.1.50")
    assert extract_client_ip(req) == "192.168.1.50"

    # X-Real-IP
    req2 = make_mock_request(headers={"X-Real-IP": "10.0.0.1"}, client_host="192.168.1.50")
    assert extract_client_ip(req2) == "10.0.0.1"

    # X-Forwarded-For single
    req3 = make_mock_request(headers={"X-Forwarded-For": "203.0.113.19"}, client_host="192.168.1.50")
    assert extract_client_ip(req3) == "203.0.113.19"

    # X-Forwarded-For multiple (client, proxy1, proxy2) -> original client
    req4 = make_mock_request(
        headers={"X-Forwarded-For": "203.0.113.19, 198.51.100.1, 192.168.1.1"},
        client_host="192.168.1.1"
    )
    assert extract_client_ip(req4) == "203.0.113.19"


@pytest.mark.asyncio
async def test_rate_limiter_allows_up_to_10_and_blocks_11th() -> None:
    limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60.0)
    ip = "192.168.1.10"

    # Check status initially
    status = await limiter.get_status(ip)
    assert status.allowed is True
    assert status.remaining == 10
    assert status.retry_after == 0.0

    # Place 10 pixels
    for i in range(10):
        status = await limiter.check_and_consume(ip)
        assert status.allowed is True
        assert status.remaining == 9 - i
        assert status.retry_after == 0.0

    # 11th should be blocked!
    status_11 = await limiter.check_and_consume(ip)
    assert status_11.allowed is False
    assert status_11.remaining == 0
    assert status_11.retry_after > 0.0
    assert status_11.retry_after <= 60.0

    # Inspect status without consuming
    status_inspect = await limiter.get_status(ip)
    assert status_inspect.allowed is False
    assert status_inspect.remaining == 0
    assert status_inspect.retry_after > 0.0


@pytest.mark.asyncio
async def test_rate_limiter_isolated_by_ip() -> None:
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0)
    ip_a = "10.0.0.1"
    ip_b = "10.0.0.2"

    # Consume all for IP A
    await limiter.check_and_consume(ip_a)
    await limiter.check_and_consume(ip_a)
    blocked_a = await limiter.check_and_consume(ip_a)
    assert blocked_a.allowed is False

    # IP B should still have full quota!
    status_b = await limiter.check_and_consume(ip_b)
    assert status_b.allowed is True
    assert status_b.remaining == 1


@pytest.mark.asyncio
async def test_rate_limiter_window_slide() -> None:
    # Short window for testing
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=0.2)
    ip = "10.0.0.5"

    assert (await limiter.check_and_consume(ip)).allowed is True
    assert (await limiter.check_and_consume(ip)).allowed is True
    assert (await limiter.check_and_consume(ip)).allowed is False

    # Wait for window to expire
    await asyncio.sleep(0.25)

    # Now allowed again!
    res = await limiter.check_and_consume(ip)
    assert res.allowed is True
    assert res.remaining == 1

