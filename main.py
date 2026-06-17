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
PW_VIDEO_API = "https://api.penpencil.co/v1/videos"


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


def get_video_url(token: str, parent_id: str, child_id: str, video_id: str) -> str:
    """
    Fetch fresh signed MPD/m3u8 URL from PW API using parentId, childId, videoId
    """
    # Try penpencil API to get fresh stream URL
    api_url = f"{PW_VIDEO_API}/{video_id}?batchId={child_id}&parentBatchId={parent_id}"
    headers = DEFAULT_HEADERS.copy()
    headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.get(api_url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        # Try to get video URL from response
        video_data = data.get("data", {})
        url = (
            video_data.get("videoUrl") or
            video_data.get("url") or
            video_data.get("hlsUrl") or
            video_data.get("dashUrl") or
            ""
        )
        return url
    except Exception:
        return ""


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "PW HLS Proxy is running",
        "usage": "/pw?url={mpd_url}&token={pw_bearer_token}&parentId={parentId}&childId={childId}&videoId={videoId}"
    }


@app.get("/pw")
def get_playlist(
    url: str,
    token: str,
    parentId: str = None,
    childId: str = None,
    videoId: str = None,
    request: Request = None
):
    base_api_url = str(request.base_url)
    encoded_token = urllib.parse.quote(token, safe='')

    # Try to fetch the URL directly first
    # If 403, try with token
    # If still 403, try getting fresh URL from PW API
    mpd_content = None
    final_url = url

    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS.copy(), timeout=15)
        if resp.status_code == 403 and token:
            headers = DEFAULT_HEADERS.copy()
            headers["Authorization"] = f"Bearer {token}"
            resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 403 and all([parentId, childId, videoId]):
            # Get fresh URL from PW API
            fresh_url = get_video_url(token, parentId, childId, videoId)
            if fresh_url:
                final_url = fresh_url
                resp = requests.get(fresh_url, headers=DEFAULT_HEADERS.copy(), timeout=15)
        resp.raise_for_status()
        mpd_content = resp.text
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=str(e))

    content = mpd_content

    # Build key proxy URL
    if videoId:
        key_api_url = f"{PW_KEY_API}?videoKey={videoId}"
    elif parentId and childId:
        key_api_url = f"{PW_KEY_API}?parentId={parentId}&childId={childId}"
    else:
        key_api_url = PW_KEY_API

    encoded_key_url = urllib.parse.quote(key_api_url, safe='')
    proxied_key_url = f"{base_api_url}key_proxy?url={encoded_key_url}&token={encoded_token}"

    # Rewrite AES-128 key URIs
    content = re.sub(
        r'URI="([^"]+)"',
        lambda m: f'URI="{proxied_key_url}"',
        content
    )

    # Make .ts segments absolute
    content = re.sub(
        r'^(?!#)(\S+\.ts\S*)$',
        lambda m: make_absolute(final_url, m.group(0)),
        content,
        flags=re.MULTILINE
    )

    # Rewrite nested .m3u8 through proxy
    def replace_m3u8(match):
        nested = make_absolute(final_url, match.group(0))
        encoded_nested = urllib.parse.quote(nested, safe='')
        params = f"url={encoded_nested}&token={encoded_token}"
        if parentId:
            params += f"&parentId={urllib.parse.quote(parentId, safe='')}"
        if childId:
            params += f"&childId={urllib.parse.quote(childId, safe='')}"
        if videoId:
            params += f"&videoId={urllib.parse.quote(videoId, safe='')}"
        return f"{base_api_url}pw?{params}"

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
    try:
        data = resp.json()
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
    return Response(
        content=resp.content,
        media_type="application/octet-stream",
        headers={"Access-Control-Allow-Origin": "*"}
    )
