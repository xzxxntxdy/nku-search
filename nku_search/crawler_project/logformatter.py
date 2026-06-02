from __future__ import annotations

import logging
from typing import Any

from scrapy.logformatter import LogFormatter


class NkuLogFormatter(LogFormatter):
    """Keep high-volume crawl logs readable during budgeted frontier expansion."""

    def dropped(self, item: Any, exception: BaseException, response, spider):
        url = ""
        if hasattr(item, "get"):
            url = str(item.get("url") or "")
        message = str(exception)
        level = logging.INFO if "reached budget" in message else logging.WARNING
        return {
            "level": level,
            "msg": "Dropped item: %(exception)s %(url)s",
            "args": {
                "exception": exception,
                "url": url,
            },
        }