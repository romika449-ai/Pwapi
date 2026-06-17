from fastapi import FastAPI, Response, Request, HTTPException
from fastapi.responses import StreamingResponse
import requests
import urllib.parse
import re

app = FastAPI(title="PW Proxy")

HEROKU_BASE = "https://anonymouspwplayerrrrr-e0949ecca662.herokuapp.com"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive"
}

@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "PW Proxy is running",
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
    base_api_url = str(request.base_url).rstrip('/')
    
    # Fix 1: Replace Heroku URLs with your API URLs
    content = content.replace(HEROKU_BASE, base_api_url)
    
    # Fix 2: Replace all segment URLs to go through /segment endpoint
    # This catches .ts, .m4s, .mp4 files and any segment URLs
    def rewrite_segment_url(match):
        original_url = match.group(0)
        # Skip if already pointing to our proxy
        if base_api_url in original_url:
            return original_url
        # Encode the URL and route through /segment
        encoded_url = urllib.parse.quote(original_url, safe='')
        return f"{base_api_url}/segment?url={encoded_url}"
    
    # Find all URLs in the content and rewrite segment URLs
    # Pattern matches http:// or https:// URLs
    url_pattern = re.compile(r'https?://[^\s"\'<>]+')
    content = url_pattern.sub(rewrite_segment_url, content)
    
    # Fix 3: Also handle relative paths (if any)
    # Replace any src/href that doesn't start with http
    def rewrite_relative(match):
        attr = match.group(1)
        value = match.group(2)
        if not value.startswith(('http://', 'https://', '/')):
            # It's a relative path, encode it
            encoded = urllib.parse.quote(value, safe='')
            return f'{attr}="{base_api_url}/segment?url={encoded}"'
        return match.group(0)
    
    content = re.sub(
        r'(src|href|url)=["\']([^"\']+)["\']',
        rewrite_relative,
        content
    )

    return Response(
        content=content,
        media_type=resp.headers.get("content-type", "application/vnd.apple.mpegurl"),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*"
        }
    )

@app.get("/key_proxy")
def proxy_key(url: str, token: str):
    heroku_url = (
        f"{HEROKU_BASE}/key_proxy"
        f"?url={urllib.parse.quote(url, safe='')}"
        f"&token={urllib.parse.quote(token, safe='')}"
    )
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
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache"
        }
    )

@app.get("/segment")
def proxy_segment(url: str):
    # Decode the URL
    decoded_url = urllib.parse.unquote(url)
    
    try:
        # Forward the request with proper headers
        headers = DEFAULT_HEADERS.copy()
        
        # Make the request with streaming
        resp = requests.get(
            decoded_url, 
            headers=headers, 
            timeout=60, 
            stream=True
        )
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch segment: {str(e)}")

    # Get content type
    content_type = resp.headers.get("content-type", "video/MP2T")
    
    # Create streaming response
    return StreamingResponse(
        resp.iter_content(chunk_size=8192),
        media_type=content_type,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache",
            "Content-Length": resp.headers.get("content-length", ""),
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*"
        }
    )

@app.options("/{path:path}")
async def options_handler(path: str):
    """Handle CORS preflight requests"""
    return Response(
        content="",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Max-Age": "86400"
        }
    )
