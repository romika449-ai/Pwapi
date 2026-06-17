from fastapi import FastAPI, Response, Request, HTTPException
import requests
import re
import urllib.parse

app = FastAPI(title="HLS Proxy API")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Origin": "https://www.pw.live",
    "Referer": "https://www.pw.live/"
}


def make_absolute(base_url: str, path: str) -> str:
    """Convert a relative URL to absolute using the base URL."""
    if path.startswith(("http://", "https://")):
        return path
    base = base_url.rsplit('/', 1)[0] + '/'
    return urllib.parse.urljoin(base, path)


def fetch_upstream(url: str, token: str) -> requests.Response:
    """Fetch a URL with auth headers, raising clean HTTP errors."""
    headers = DEFAULT_HEADERS.copy()
    headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp
    except requests.HTTPError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Upstream error: {e}"
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch: {e}")


def proxy_url(base_api_url: str, target_url: str, endpoint: str, encoded_token: str) -> str:
    encoded = urllib.parse.quote(target_url, safe='')
    return f"{base_api_url}{endpoint}?url={encoded}&token={encoded_token}"


@app.get("/")
def root():
    return {"status": "ok", "message": "HLS Proxy is running"}


@app.get("/pw")
def get_playlist(url: str, token: str, request: Request):
    resp = fetch_upstream(url, token)
    content = resp.text

    base_api_url = str(request.base_url)
    encoded_token = urllib.parse.quote(token, safe='')

    # Rewrite AES-128 key URIs → /key_proxy
    def replace_key_uri(match: re.Match) -> str:
        absolute = make_absolute(url, match.group(1))
        return f'URI="{proxy_url(base_api_url, absolute, "key_proxy", encoded_token)}"'

    content = re.sub(r'URI="([^"]+)"', replace_key_uri, content)

    # Rewrite .ts segments → absolute URLs
    def replace_segment(match: re.Match) -> str:
        return make_absolute(url, match.group(0))

    content = re.sub(
        r'^(?!#)(\S+\.ts\S*)$',
        replace_segment,
        content,
        flags=re.MULTILINE
    )

    # Rewrite nested .m3u8 → back through /pw so they get rewritten too
    def replace_nested_m3u8(match: re.Match) -> str:
        absolute = make_absolute(url, match.group(0))
        return proxy_url(base_api_url, absolute, "pw", encoded_token)

    content = re.sub(
        r'^(?!#)(\S+\.m3u8\S*)$',
        replace_nested_m3u8,
        content,
        flags=re.MULTILINE
    )

    return Response(content=content, media_type="application/vnd.apple.mpegurl")


@app.get("/key_proxy")
def proxy_key(url: str, token: str):
    resp = fetch_upstream(url, token)
    return Response(content=resp.content, media_type="application/octet-stream")
