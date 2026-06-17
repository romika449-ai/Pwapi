from fastapi import FastAPI, Response, Request, HTTPException
import requests
import re
import urllib.parse

app = FastAPI(title="PW DASH Proxy")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
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


def get_clean_mpd_url(url: str) -> str:
    """Return just the MPD URL without extra query params."""
    if ".mpd&" in url:
        return url.split(".mpd&")[0] + ".mpd"
    if ".mpd?" in url:
        return url.split(".mpd?")[0] + ".mpd"
    return url


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "PW DASH Proxy is running",
        "usage": "/pw?url={mpd_url}&parentId={parentId}&childId={childId}&videoId={videoId}&token={pw_bearer_token}"
    }


@app.get("/pw")
def get_mpd(
    url: str,
    token: str,
    parentId: str = None,
    childId: str = None,
    videoId: str = None,
    request: Request = None
):
    # Step 1: Clean MPD URL
    clean_url = get_clean_mpd_url(url)

    # Step 2: Fetch MPD with token
    resp = fetch(clean_url, token)
    content = resp.text

    base_api_url = str(request.base_url)
    encoded_token = urllib.parse.quote(token, safe='')

    # Step 3: Build PW key API URL
    key_params = {}
    if parentId:
        key_params["parentId"] = parentId
    if childId:
        key_params["childId"] = childId
    if videoId:
        key_params["videoId"] = videoId

    key_api_url = PW_KEY_API + "?" + urllib.parse.urlencode(key_params)
    encoded_key_url = urllib.parse.quote(key_api_url, safe='')
    proxied_key_url = f"{base_api_url}key_proxy?url={encoded_key_url}&token={encoded_token}"

    # Step 4: Rewrite licenseUrl → our /key_proxy
    content = re.sub(
        r'licenseUrl="([^"]+)"',
        lambda m: f'licenseUrl="{proxied_key_url}"',
        content
    )

    # Step 5: Rewrite dashif:laurl tag
    content = re.sub(
        r'(<dashif:laurl[^>]*>)[^<]*(</dashif:laurl>)',
        lambda m: f'{m.group(1)}{proxied_key_url}{m.group(2)}',
        content
    )

    # Step 6: Make initialization segment URLs absolute
    content = re.sub(
        r'initialization="([^"]+)"',
        lambda m: f'initialization="{make_absolute(clean_url, m.group(1))}"',
        content
    )

    # Step 7: Make media segment template URLs absolute
    content = re.sub(
        r'\bmedia="([^"$][^"]*)"',
        lambda m: f'media="{make_absolute(clean_url, m.group(1))}"',
        content
    )

    # Step 8: Make BaseURL absolute
    content = re.sub(
        r'<BaseURL>([^<]+)</BaseURL>',
        lambda m: f'<BaseURL>{make_absolute(clean_url, m.group(1).strip())}</BaseURL>',
        content
    )

    return Response(
        content=content,
        media_type="application/dash+xml",
        headers={"Access-Control-Allow-Origin": "*"}
    )


@app.get("/key_proxy")
def proxy_key(url: str, token: str):
    """Fetch ClearKey from PW key API and return raw bytes."""
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
