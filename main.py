from fastapi import FastAPI, Response, Request, HTTPException
from fastapi.responses import StreamingResponse
import requests
import urllib.parse

app = FastAPI(title="PW Proxy")

HEROKU_BASE = "https://anonymouspwplayerrrrr-e0949ecca662.herokuapp.com"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
}


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "PW Proxy running",
        "usage": "/pw?url={mpd_url}&token={token}&parentId={parentId}&childId={childId}&videoId={videoId}"
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
    # Build Heroku URL with all params
    params = {"url": url, "token": token}
    if parentId:
        params["parentId"] = parentId
    if childId:
        params["childId"] = childId
    if videoId:
        params["videoId"] = videoId

    heroku_url = f"{HEROKU_BASE}/pw?" + urllib.parse.urlencode(params)

    try:
        resp = requests.get(heroku_url, headers=DEFAULT_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=str(e))

    content = resp.text
    base_api_url = str(request.base_url)

    # Rewrite Heroku URLs in m3u8 → our Render URL
    content = content.replace(
        f"{HEROKU_BASE}/pw",
        f"{base_api_url}pw"
    )
    content = content.replace(
        f"{HEROKU_BASE}/key_proxy",
        f"{base_api_url}key_proxy"
    )
    content = content.replace(
        f"{HEROKU_BASE}/sec-prod-mediacdn",
        f"{base_api_url}sec-prod-mediacdn"
    )

    return Response(
        content=content,
        media_type=resp.headers.get("content-type", "application/vnd.apple.mpegurl"),
        headers={"Access-Control-Allow-Origin": "*"}
    )


@app.get("/key_proxy")
def proxy_key(url: str, token: str):
    # Forward to Heroku key_proxy
    heroku_url = f"{HEROKU_BASE}/key_proxy?url={urllib.parse.quote(url, safe='')}&token={urllib.parse.quote(token, safe='')}"
    try:
        resp = requests.get(heroku_url, headers=DEFAULT_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=str(e))

    return Response(
        content=resp.content,
        media_type="application/octet-stream",
        headers={"Access-Control-Allow-Origin": "*"}
    )


@app.get("/segment")
def proxy_segment(url: str):
    """Proxy .ts / .m4s video segments — streams directly for fast playback"""
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=30, stream=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=str(e))

    return StreamingResponse(
        resp.iter_content(chunk_size=8192),
        media_type=resp.headers.get("content-type", "video/MP2T"),
        headers={"Access-Control-Allow-Origin": "*"}
    )
