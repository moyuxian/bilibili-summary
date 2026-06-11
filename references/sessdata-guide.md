# Bilibili SESSDATA Guide

## What is SESSDATA
A session cookie from bilibili.com that authenticates API requests. Equivalent to being logged in.

## How to get it
1. Log into bilibili.com in a browser
2. F12 → Application → Cookies → `https://www.bilibili.com`
3. Copy the `SESSDATA` value (looks like `a1b2c3d4%2C1234567890%2Cxxxx%2Axx...`)

## Storage
Stored in `~/.hermes/.env` as `BILIBILI_SESSDATA=...`. Script auto-loads it.

## Validity
~几个月 (a few months). When videos start failing with empty subtitle arrays or 412 errors, regenerate.

## Security
- Treat as a login credential — don't share publicly
- Only used for read-only API calls (video info, subtitles, playback URLs)
- No write operations (no posting, no account changes)

## Ban risk
Low for normal usage (occasional video lookups). Would only be an issue with high-frequency scraping (hundreds of requests/minute). Hermes usage pattern is safe.

## Without SESSDATA
- Video info API: works for public videos
- Subtitle API: returns empty arrays for most videos (CC subtitles invisible)
- Playback API: works for most public videos, some return 412
- ASR fallback: still works (downloads audio via playback API + transcribes)
