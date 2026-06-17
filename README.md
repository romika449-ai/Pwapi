# HLS Proxy API

A FastAPI proxy for Physics Wallah HLS streams. Rewrites `.m3u8` playlists so any standard video player can play auth-protected streams.

## Endpoints

| Endpoint | Params | Description |
|----------|--------|-------------|
| `GET /pw` | `url`, `token` | Fetches and rewrites an HLS playlist |
| `GET /key_proxy` | `url`, `token` | Proxies AES-128 decryption keys |
| `GET /` | — | Health check |

## Usage

```
https://your-app.onrender.com/pw?url={m3u8_url}&token={pw_bearer_token}
```

Pass this URL into any HLS-compatible player (VLC, hls.js, etc).

---

## Deploy on Render

### 1. Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/hls-proxy.git
git push -u origin main
```

### 2. Create a Render Web Service

1. Go to [render.com](https://render.com) and sign in
2. Click **New → Web Service**
3. Connect your GitHub repo
4. Render auto-detects settings from `render.yaml` — just click **Deploy**

### 3. Your API is live at:
```
https://hls-proxy.onrender.com
```

---

## Run Locally

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

API will be at `http://localhost:8000`
Swagger docs at `http://localhost:8000/docs`
