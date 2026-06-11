# API Notes — Bilibili Summary Skill

## MiMo-V2.5-ASR API (Xiaomi)

**Endpoint:** `{XIAOMI_BASE_URL}/chat/completions` (OpenAI-compatible)

**Critical: message format is `input_audio`, NOT `audio_url`:**
```json
{
  "model": "mimo-v2.5-asr",
  "messages": [{
    "role": "user",
    "content": [{
      "type": "input_audio",
      "input_audio": {
        "data": "data:audio/wav;base64,{BASE64}",
        "format": "wav"
      }
    }]
  }]
}
```

Common mistakes:
- Using `audio_url` type → 400 error "ASR requires exactly one input_audio part"
- Using bare base64 in `data` → 400 error "must be a valid data URL with mime type prefix"
- Supported formats: `wav`, `mp3` only
- Base64 size limit: ~10MB per request

**Token plan base URL:** `https://token-plan-cn.xiaomimimo.com/v1`
**Standard base URL:** `https://api.xiaomimimo.com/v1`

## Bilibili APIs

### Video Info
```
GET https://api.bilibili.com/x/web-interface/view?bvid=BV...
→ { data: { title, cid, duration, owner: {name}, pages: [...] } }
```
No auth needed for public videos.

### Subtitles
```
GET https://api.bilibili.com/x/player/v2?bvid=BV...&cid={cid}
→ { data: { subtitle: { subtitles: [{lan, lan_doc, subtitle_url}] } } }
```
- **SESSDATA required**: Without it, `subtitles` array is empty for virtually all videos. Store in `~/.hermes/.env` as `BILIBILI_SESSDATA`.
- **Empty subtitle_url**: Some entries in the array have `subtitle_url: ""` (empty string). Must guard against this before fetching — causes `Invalid URL ''` error otherwise.
- Prefers Chinese (`zh-CN`, `zh-Hans`, `ai-zh`), falls back to first available
- Subtitle JSON format: `{body: [{from, to, content}]}`
- Subtitle URLs prefixed with `//` → needs `https:` prepended

### Audio Stream (DASH)
```
GET https://api.bilibili.com/x/player/wbi/playurl?bvid=BV...&cid={cid}&fnval=16
→ { data: { dash: { audio: [{baseUrl, bandwidth, codecs}] } } }
```
- `fnval=16` requests DASH format (separates audio/video)
- Audio streams sorted by bandwidth (highest quality first)
- Audio URL requires `Referer: https://www.bilibili.com` header
- Without SESSDATA, some videos return 412 on playback API

### yt-dlp Status
- Bilibili returns HTTP 412 (Precondition Failed) to yt-dlp as of 2026-06
- Do NOT rely on yt-dlp for Bilibili audio; use the playback API directly

## Audio Processing Pipeline

1. Download via B站 playback API → m4a file
2. ffmpeg convert: mono, 16kHz, 48kbps mp3 (minimize size)
3. If >7MB → split into 5-min chunks via ffmpeg `-ss`/`-t`
4. Transcribe each chunk separately, concatenate results
