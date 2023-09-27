from time import time
from traceback import format_exc
from urllib.parse import urljoin

from blosc2 import Codec, Filter, compress, decompress
from brotli_asgi import BrotliMiddleware
from diskcache import Cache
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from httpx import AsyncClient
from promplate import ChainContext

from env import env

client = AsyncClient(http2=True, base_url=env.baseurl)
cache = Cache(".cache", eviction_policy="none", statics=True)
app = FastAPI(openapi_url=None)
app.add_middleware(BrotliMiddleware)
app.add_middleware(CORSMiddleware, allow_origins="*", max_age=env.min_age or None)


def decorate_body(body: bytes):
    if not env.replace:
        return body

    body = body.replace(env.baseurl.encode(), env.replace.encode())
    for site in env.proxy_sites | env.bypass_sites:
        body = body.replace(site.encode(), f"/proxy/{site}".encode())
    return body


def decorate_headers(headers: dict[str, str]):
    if "location" in headers:
        headers["location"] = headers["location"].replace(env.baseurl, env.replace)

    return dict(headers)


def print_information(status: int, body: bytes, headers: dict, /):
    print(f"\n > {status} | {len(body)} bytes\n")
    for k, v in headers.items():
        print(f"{k:>20}: {v}")
    print()


async def fetch(url: str):
    cache_key = url
    hit = cache.get(cache_key)

    hits, misses = cache.stats()
    common_headers = {"x-diskcache-hits": str(hits), "x-diskcache-misses": str(misses)}

    def make_response(body, status=None, headers=None, /):
        return Response(decorate_body(body), status, decorate_headers(ChainContext(common_headers, headers)))

    if not hit or env.min_age and (age := time() - hit["timestamp"]) > env.min_age:
        print(f"\n < fetch {url!r}")

        res = await client.get(url)

        res_headers = res.headers.copy()
        res_body = res.read()
        res_status = res.status_code

        for h in env.excluded_headers:
            res_headers.pop(h, None)

        print_information(res_status, res_body, res_headers)

        if res_status < 400 or res_status:
            cache.set(
                cache_key,
                {
                    "body": compress(res_body, 1, 9, Filter.NOFILTER, Codec.LZ4),
                    "headers": dict(res_headers),
                    "status": res_status,
                    "timestamp": time(),
                },
            )
            age = 0
        elif hit:
            res_body = decompress(hit["body"])
            res_status = hit["status"]
            res_headers = hit["headers"]
        else:
            age = 0

        common_headers["x-diskcache-age"] = f"{age:.0f}"

        return make_response(res_body, res_status, res_headers)

    common_headers["x-diskcache-age"] = f"{time() - hit['timestamp']:.0f}"

    return make_response(decompress(hit["body"]), hit["status"], hit["headers"])


if env.replace and env.proxy_sites:

    @app.get(f"/{env.proxy_slug}/{{path:path}}")
    async def proxy_external_resources(path: str, request: Request):
        for i in env.bypass_sites:
            if path.startswith(i):
                return Response(None, 204)
        return await fetch(f"{path}?{request.url.query}")


@app.get("/{path:path}")
async def handle_get_request(path: str | None = ""):
    url = urljoin(env.baseurl, path)

    return await fetch(url)


@app.head("/{path:path}")
async def handle_head_request(path: str | None = ""):
    res: Response = await handle_get_request(path)
    return Response(None, res.status_code, res.headers)


@app.exception_handler(Exception)
async def handle_exception(*_):
    return Response(format_exc(), 500, media_type="text/plain")
