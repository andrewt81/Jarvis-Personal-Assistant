from jarvis.auth.rate_limit import AuthenticationRateLimiter, RateLimit


def test_rate_limiter_expires_failures_and_clears_successful_account() -> None:
    current = [100.0]
    limiter = AuthenticationRateLimiter(
        now=lambda: current[0],
        client_limit=RateLimit(3, 60),
        account_limit=RateLimit(2, 30),
    )

    limiter.failure("client", "account")
    limiter.failure("client", "account")
    assert limiter.retry_after("client", "account") == 31

    limiter.success("account")
    assert limiter.retry_after("client", "account") is None

    current[0] = 161.0
    assert limiter.retry_after("client", "account") is None
