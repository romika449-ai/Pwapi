from fastapi import FastAPI, Response, Request, HTTPException
import requests
import re
import urllib.parse

app = FastAPI(title="PW DASH Proxy")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Origin": "https://www.pw.live",
    "Referer": "https://www.pw.live/"
}

PW_KEY_API = "https://api.pw.live/video/key"


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
        "message": "PW DASH Proxy is running",
        "usage": "/pw?url={mpd_url}&parentId={parentId}&childId={childId}&videoId={videoId}&token={token}"
    }


@app.get("/pw")
def get_mpd(
    url: str,
    token: str,
    parentId: str,
    childId: str,
    videoId: str = None,
    request: Request = None
):
    # Fetch MPD manifest directly (no token needed for CloudFront)
    resp = fetch(url)
    content = resp.text

    base_api_url = str(request.base_url)
    encoded_token = urllib.parse.quote(token, safe='')

    # Build PW key API URL with parentId, childId, videoId
    key_params = {"parentId": parentId, "childId": childId}
    if videoId:
        key_params["videoId"] = videoId

    key_api_url = PW_KEY_API + "?" + urllib.parse.urlencode(key_params)
    encoded_key_url = urllib.parse.quote(key_api_url, safe='')
    proxied_key_url = f"{base_api_url}key_proxy?url={encoded_key_url}&token={encoded_token}"

    # Rewrite licenseUrl
    content = re.sub(
        r'licenseUrl="([^"]+)"',
        lambda m: f'licenseUrl="{proxied_key_url}"',
        content
    )

    # Rewrite dashif:laurl
    content = re.sub(
        r'(<dashif:laurl[^>]*>)[^<]*(</dashif:laurl>)',
        lambda m: f'{m.group(1)}{proxied_key_url}{m.group(2)}',
        content
    )

    # Make initialization segments absolute
    content = re.sub(
        r'initialization="([^"]+)"',
        lambda m: f'initialization="{make_absolute(url, m.group(1))}"',
        content
    )

    # Make media segment templates absolute
    content = re.sub(
        r'\bmedia="([^"$][^"]*)"',
        lambda m: f'media="{make_absolute(url, m.group(1))}"',
        content
    )

    # Make BaseURL absolute
    content = re.sub(
        r'<BaseURL>([^<]+)</BaseURL>',
        lambda m: f'<BaseURL>{make_absolute(url, m.group(1).strip())}</BaseURL>',
        content
    )

    return Response(
        content=content,
        media_type="application/dash+xml",
        headers={"Access-Control-Allow-Origin": "*"}
    )


@app.get("/key_proxy")
def proxy_key(url: str, token: str):
    resp = fetch(url, token)
    try:
        data = resp.json()
        key_hex = (
            data.get("key") or
            data.get("data", {}).get("key", "") or
            data.get("keys", [{}])[0].get("k", "")
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
    return Response(
        content=resp.content,
        media_type="application/octet-stream",
        headers={"Access-Control-Allow-Origin": "*"}
    )
