import httpx
import pytest

from vps_tracker.http import Requester


class FakeTime:
    def __init__(self):
        self.now = 0.0

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_throttle_retries_and_redirects():
    time = FakeTime()
    starts = []

    def handler(request):
        starts.append(time.now)
        if len(starts) == 1:
            return httpx.Response(503)
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/offers"})
        return httpx.Response(200, text="offers")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        requester = Requester(client, clock=time.clock, sleep=time.sleep)
        assert requester.get("https://www.vendor.com/start").text == "offers"
        requester.get("https://app.vendor.com/offers")
    assert starts == [0, 2, 4, 6]


def test_retry_after():
    time = FakeTime()
    starts = []

    def handler(request):
        starts.append(time.now)
        if len(starts) == 1:
            return httpx.Response(429, headers={"retry-after": "8"})
        return httpx.Response(200)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        Requester(client, clock=time.clock, sleep=time.sleep).get("https://vendor.com/")
    assert starts == [0, 8]


@pytest.mark.parametrize("failure", ["http", "connection"])
def test_retry_exhaustion(failure):
    time = FakeTime()
    calls = []

    def handler(request):
        calls.append(time.now)
        if failure == "connection":
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(500)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises((httpx.HTTPStatusError, httpx.ConnectError)):
            Requester(client, clock=time.clock, sleep=time.sleep).get("https://vendor.com/")
    assert calls == [0, 2, 4]


def test_forbidden_not_retried():
    calls = []
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: calls.append(request) or httpx.Response(403))
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            Requester(client).get("https://vendor.com/")
    assert len(calls) == 1


def test_https_downgrade_refused():
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(302, headers={"location": "http://vendor.com/"})
        )
    ) as client:
        with pytest.raises(ValueError, match="非 HTTPS"):
            Requester(client).get("https://vendor.com/")
