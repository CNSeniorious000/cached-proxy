import re
from asyncio import Semaphore, create_task, gather, run
from contextlib import suppress
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from httpx import AsyncClient, HTTPError

base_url = "http://localhost:8000"
start_url = input("start from: ")


client = AsyncClient(http2=True, base_url=base_url, timeout=60)

sem = Semaphore(500)

count = 0

url_in_css = re.compile(r"url\((.*?)\)")


def is_same_origin(link):
    url = urljoin(base_url, link)
    return url.startswith(base_url)


def format_url(url: str):
    return url.strip('"').strip("\\").strip('"')


async def get_links(url: str):
    with suppress(HTTPError):
        for i in [".png", ".jpg", ".js"]:
            if url.endswith(i):
                async with sem:
                    await client.head(url)
                return []

        async with sem:
            response = await client.get(url, headers={"accept-type": ""})

            if url.endswith(".css"):
                return [i for i in url_in_css.findall(response.text) if "data:" not in i]

            if "html" not in response.headers.get("content-type", ""):
                return []

            # dom = BeautifulSoup(response.text, features="html.parser")
            dom = BeautifulSoup(response.text, features="lxml")

            return [
                *[format_url(i.get("href", "")) for i in dom.find_all("link")],
                *[format_url(i.get("href", "")) for i in dom.find_all("a")],
                *[format_url(i.get("src", "")) for i in dom.find_all("script")],
                *[format_url(i.get("src", "")) for i in dom.find_all("img")],
                *[format_url(i.get("src", "")) for i in dom.find_all("video")],
                *[format_url(i.get("src", "")) for i in dom.find_all("iframe")],
                *[format_url(i.get("src", "")) for i in dom.find_all("source")],
            ]

    return []


async def crawl(url: str, visited_urls):
    global count

    if url in visited_urls:
        return

    visited_urls.add(url)
    count += 1

    for i in ["/ar", "/es", "/en", "/proxy"]:
        if url.startswith(i):
            return

    if not url.startswith("/zh-hans") and count > 100:
        return

    tasks = []

    links = await get_links(url)

    from random import random, shuffle

    shuffle(links)

    for i in links:
        if i and is_same_origin(i) and not i.startswith("#") and i not in visited_urls:
            tasks.append(create_task(crawl(i, visited_urls)))

    print(f"{count:>7} + {len(tasks):>4} > {url}")
    await gather(*tasks)


async def main():
    await crawl(start_url, set())


if __name__ == "__main__":
    run(main())
