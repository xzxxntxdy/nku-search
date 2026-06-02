from __future__ import annotations

import scrapy


class NkuPageItem(scrapy.Item):
    url = scrapy.Field()
    title = scrapy.Field()
    text = scrapy.Field()
    html = scrapy.Field()
    anchors = scrapy.Field()
    outgoing_links = scrapy.Field()
    content_type = scrapy.Field()
    filetype = scrapy.Field()
    section = scrapy.Field()
    category = scrapy.Field()
    fetched_at = scrapy.Field()
    status = scrapy.Field()
    depth = scrapy.Field()
    source_spider = scrapy.Field()
