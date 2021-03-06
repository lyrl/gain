import asyncio
import re
from pybloomfilter import BloomFilter

import aiohttp

from gain.request import fetch
from .log import logger


class Parser:
    def __init__(self, rule, item=None):
        self.rule = rule
        self.item = item
        self.parsing_urls = []
        self.pre_parse_urls = []
        self.filter_urls = BloomFilter(10000000, 0.01)
        self.done_urls = []

    def add(self, urls):
        url = '{}'.format(urls)
        if url.encode('utf-8') not in self.filter_urls:
            self.filter_urls.add(url.encode('utf-8'))
            self.pre_parse_urls.append(url)

    def parse_urls(self, html):
        urls = re.findall(self.rule, html)
        for url in urls:
            self.add(url)

    async def parse_item(self, html):
        item = self.item(html)
        await item.save()
        self.item._item_count += 1
        return item

    async def execute_url(self, spider, session, semaphore, url):
        html = await fetch(url, session, semaphore)

        if html is None:
            spider.error_urls.append(url)
            self.pre_parse_urls.append(url)
            return
        if url in spider.error_urls:
            spider.error_urls.remove(url)
        spider.urls_count += 1
        self.parsing_urls.remove(url)
        self.done_urls.append(url)
        if self.item is not None:
            await self.parse_item(html)
            logger.info('Parsed({}/{}): {}'.format(len(self.done_urls), len(self.filter_urls), url))
        else:
            spider.parse(html)
            logger.info('Followed({}/{}): {}'.format(len(self.done_urls), len(self.filter_urls), url))

    async def task(self, spider, semaphore):
        with aiohttp.ClientSession() as session:
            while spider.is_running():
                if len(self.pre_parse_urls) == 0:
                    await asyncio.sleep(0.5)
                    continue
                url = self.pre_parse_urls.pop()
                self.parsing_urls.append(url)
                asyncio.ensure_future(self.execute_url(spider, session, semaphore, url))
