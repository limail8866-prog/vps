import logging
from collections.abc import Callable
from contextvars import ContextVar

from ..config import get_config
from ..http import Requester
from ..models import Plan

LOG = logging.getLogger(__name__)
SOURCE_OBSERVATIONS: ContextVar[dict | None] = ContextVar("vps_source_observations", default=None)


def fetch_from_sources(
    provider: str,
    parser: Callable[[str, str], list[Plan]],
    http: Requester,
) -> list[Plan]:
    failures = []
    observations = SOURCE_OBSERVATIONS.get()
    record = {"selected_url": None, "failures": []}
    if observations is not None:
        observations[provider] = record
    for url in get_config().sources[provider]:
        try:
            plans = parser(http.get(url).text, url)
            if not plans:
                raise ValueError("没有可售套餐")
            record["selected_url"] = url
            return plans
        except Exception as exc:
            reason = f"{url}：{type(exc).__name__}: {exc}"
            failures.append(reason)
            record["failures"].append({"url": url, "reason": f"{type(exc).__name__}: {exc}"})
            LOG.warning("%s 来源失效，尝试下一个：%s", provider, reason)
    raise RuntimeError(f"{provider} 所有来源均失败；" + "；".join(failures))
