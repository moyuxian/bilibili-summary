---
name: bilibili-summary
description: "Bilibili video summarization: fetch CC subtitles or fall back to MiMo-V2.5-ASR transcription, then summarize with LLM."
platforms: [linux, macos, windows]
tags: [bilibili, video, summarization, asr, transcription]
related_skills: [youtube-content]
---

# Bilibili Video Summarizer

When the user shares a Bilibili video URL (bilibili.com/video/BV... or b23.tv short link), use this skill to extract the transcript and summarize it.

## Workflow

1. **Extract transcript** using the helper script (subtitle-first, ASR fallback)
2. **Summarize** the transcript with the current LLM

## Setup

```bash
pip install requests
# ffmpeg must be installed (apt install ffmpeg / brew install ffmpeg)
```

Environment variables (already configured in ~/.hermes/.env):
- `XIAOMI_API_KEY` — for MiMo-V2.5-ASR API
- `XIAOMI_BASE_URL` — API base URL (token-plan-cn.xiaomimimo.com/v1)

## Helper Script

`SKILL_DIR` = directory containing this SKILL.md.

### Basic usage (subtitle → ASR fallback, JSON output)
```bash
python3 SKILL_DIR/scripts/bilibili_summary.py "https://www.bilibili.com/video/BV1xx411c7XW"
```

### Plain text output (for piping into LLM)
```bash
python3 SKILL_DIR/scripts/bilibili_summary.py "URL" --text-only
```

### With timestamps
```bash
python3 SKILL_DIR/scripts/bilibili_summary.py "URL" --text-only --timestamps
```

### Force ASR (skip subtitle check)
```bash
python3 SKILL_DIR/scripts/bilibili_summary.py "URL" --text-only --force-asr
```

### With explicit SESSDATA (usually not needed — auto-loaded from BILIBILI_SESSDATA in ~/.hermes/.env)
```bash
python3 SKILL_DIR/scripts/bilibili_summary.py "URL" --sessdata "your_sessdata_here"
```

SESSDATA is auto-loaded from the `BILIBILI_SESSDATA` env var if `--sessdata` is not passed. It is **effectively required** for the subtitle path — without it, the subtitle API returns empty arrays for most videos even when CC subtitles exist.

## Output Format (JSON)

```json
{
  "bvid": "BV1xx411c7XW",
  "title": "视频标题",
  "owner": "UP主名称",
  "duration": 600,
  "source": "subtitle|asr",
  "text": "完整字幕/转录文本",
  "subtitle_count": 42
}
```

`source` indicates whether text came from CC subtitles or ASR transcription.

## Summarization

After extracting the transcript, summarize it for the user. Default format:

1. **一句话总结** — 1-2 sentences capturing the core message
2. **要点** — 3-7 key points as bullet list
3. **时间线** (if timestamps available) — major sections with timestamps

For long videos (>10K chars), chunk the text and summarize each chunk before merging.

## Technical Details

- Audio downloaded via B站 playback API (no yt-dlp needed — B站 returns 412 to yt-dlp)
- Long audio auto-split into 5-min chunks, each <10MB for ASR API
- ffmpeg converts to mono 16kHz 48kbps mp3 to minimize size
- ASR uses `mimo-v2.5-asr` model via OpenAI-compatible API
- Subtitle detection uses `/x/player/v2` endpoint
- Full API details: see `references/api-notes.md`
- SESSDATA setup & validity: see `references/sessdata-guide.md`

## Pitfalls

- **MiMo ASR message format**: must use `input_audio` type (NOT `audio_url`). Data must be a full data URL (`data:audio/wav;base64,...`), not bare base64.
- **yt-dlp broken for Bilibili**: HTTP 412 as of 2026-06. Use B站 playback API (`/x/player/wbi/playurl?fnval=16`) instead.
- **B站 subtitle API needs SESSDATA**: Without `BILIBILI_SESSDATA` in `.env`, the `/x/player/v2` endpoint returns empty subtitle arrays for virtually all videos — even ones that clearly have CC subtitles. SESSDATA is effectively mandatory for the subtitle path. The script auto-loads it from env.
- **Empty subtitle_url in array**: Some subtitle entries in the API response have `subtitle_url: ""` (empty string). The script must guard against this — attempting to fetch an empty URL causes `Invalid URL ''` errors.
- **Long audio**: ASR API has ~10MB base64 limit. Script auto-chunks, but very long videos (1h+) may need multiple API calls.

## Error Handling

- **No subtitles + ASR fails**: tell the user; suggest checking if the video is region-locked or needs SESSDATA
- **Audio too large**: auto-chunked; if individual chunks still exceed limit, report error
- **412 / auth errors**: B站 playback API may need SESSDATA for some videos
- **Short video (< 1 min)**: subtitles may be empty; ASR fallback should still work

## Notes

- B站 CC 字幕是 AI 生成的，大部分热门视频都有。**必须配置 SESSDATA** 才能通过 API 拿到（已存入 `~/.hermes/.env` 的 `BILIBILI_SESSDATA`）
- ASR fallback 需要下载音频 + 调小米 API，耗时较长（短视频 ~30s，长视频 2-5min）
- 测试结果（2026-06-11）：
  - 英文 MV（Rick Astley）：字幕 ✅（12种语言），ASR ✅
  - 英文课程（Docker）：字幕 ✅，ASR ✅
  - 中文课程（李宏毅 ML，长视频）：字幕 ✅，ASR ✅（自动分 8 片）
  - 中文科普（短片）：字幕 URL 空 → ASR fallback ✅
- 用户的 SESSDATA 有效期约几个月，过期需重新获取
