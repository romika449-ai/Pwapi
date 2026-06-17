from fastapi import FastAPI, Response, Request, HTTPException
import requests
import re
import urllib.parse

app = FastAPI(title="PW HLS Proxy")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Origin": "https://www.pw.live",
    "Referer": "https://www.pw.live/"
}

PW_KEY_API = "https://api.penpencil.co/v1/videos/get-hls-key"


def fetch(url: str, token: str = None) -> requests.Response:
    headers = DEFAULT_HEADERS.copy()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=str(e))


def make_absolute(base_url: str, path: str) -> str:
    if path.startswith(("http://", "https://")):
        return path
    base = base_url.rsplit('/', 1)[0] + '/'
    return urllib.parse.urljoin(base, path)


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "PW HLS Proxy is running",
        "usage": "/pw?url={m3u8_or_mpd_url}&token={pw_bearer_token}"
    }


@app.get("/pw")
def get_playlist(url: str, token: str, request: Request):
    base_api_url = str(request.base_url)
    encoded_token = urllib.parse.quote(token, safe='')

    # Fetch the playlist (m3u8 or mpd)
    resp = fetch(url, token)
    content = resp.text

    # Extract videoKey from URL (the UUID part)
    # e.g. https://d1d34p8vz63oiq.cloudfront.net/61ce614c-893c-459d-855b-8d349727fc31/master.mpd
    video_key_match = re.search(
        r'cloudfront\.net/([a-f0-9\-]{36})/',
        url
    )
    video_key = video_key_match.group(1) if video_key_match else None

    # Build key API URL
    if video_key:
        key_api_url = f"{PW_KEY_API}?videoKey={video_key}"
    else:
        key_api_url = PW_KEY_API

    encoded_key_url = urllib.parse.quote(key_api_url, safe='')
    proxied_key_url = f"{base_api_url}key_proxy?url={encoded_key_url}&token={encoded_token}"

    # Rewrite AES-128 key URIs → /key_proxy
    def replace_key_uri(match):
        return f'URI="{proxied_key_url}"'

    content = re.sub(r'URI="([^"]+)"', replace_key_uri, content)

    # Make .ts segment URLs absolute
    def replace_segment(match):
        return make_absolute(url, match.group(0))

    content = re.sub(
        r'^(?!#)(\S+\.ts\S*)$',
        replace_segment,
        content,
        flags=re.MULTILINE
    )

    # Make nested .m3u8 URLs absolute (master playlist → variant)
    def replace_m3u8(match):
        nested = make_absolute(url, match.group(0))
        encoded_nested = urllib.parse.quote(nested, safe='')
        return f"{base_api_url}pw?url={encoded_nested}&token={encoded_token}"

    content = re.sub(
        r'^(?!#)(\S+\.m3u8\S*)$',
        replace_m3u8,
        content,
        flags=re.MULTILINE
    )

    return Response(
        content=content,
        media_type="application/vnd.apple.mpegurl",
        headers={"Access-Control-Allow-Origin": "*"}
    )


@app.get("/key_proxy")
def proxy_key(url: str, token: str):
    resp = fetch(url, token)

    # PW key API returns JSON with key
    try:
        data = resp.json()
        # Try different response shapes
        key_hex = (
            data.get("key") or
            data.get("data", {}).get("key") or
            data.get("encKey") or
            data.get("data", {}).get("encKey") or
            ""
        )
        if key_hex:
            key_bytes = bytes.fromhex(key_hex.replace("-", ""))
            return Response(
                content=key_bytes,
                media_type="application/octet-stream",
                headers={"Access-Control-Allow-Origin": "*"}
            )
    except Exception:
        pass

    # Fallback: return raw response
    return Response(
        content=resp.content,
        media_type="application/octet-stream",
        headers={"Access-Control-Allow-Origin": "*"}
    )
