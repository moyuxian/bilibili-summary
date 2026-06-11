#!/usr/bin/env python3
"""
Bilibili video transcript extractor.

Workflow:
1. Parse BV ID from URL
2. Fetch video metadata (title, cid) from Bilibili API
3. Try to get CC subtitles
4. If no subtitles → download audio via yt-dlp → transcribe with MiMo-V2.5-ASR
5. Output structured JSON with title + transcript text
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlparse

import requests

BILIBILI_API = "https://api.bilibili.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def parse_bvid(url_or_bvid: str) -> str:
    """Extract BV ID from a Bilibili URL or raw BV string."""
    # Already a BV ID
    if re.match(r"^BV[\w]{10}$", url_or_bvid):
        return url_or_bvid
    # Parse from URL
    m = re.search(r"(BV[\w]{10})", url_or_bvid)
    if m:
        return m.group(1)
    raise ValueError(f"Cannot extract BV ID from: {url_or_bvid}")


def get_video_info(bvid: str, sessdata: str = None) -> dict:
    """Get video title, cid, pages from Bilibili API."""
    headers = {"User-Agent": USER_AGENT, "Referer": "https://www.bilibili.com"}
    if sessdata:
        headers["Cookie"] = f"SESSDATA={sessdata}"

    # Get basic info
    resp = requests.get(
        f"{BILIBILI_API}/x/web-interface/view",
        params={"bvid": bvid},
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data["code"] != 0:
        raise RuntimeError(f"Bilibili API error: {data.get('message', data['code'])}")

    view = data["data"]
    return {
        "bvid": bvid,
        "title": view["title"],
        "desc": view.get("desc", ""),
        "duration": view["duration"],
        "owner": view["owner"]["name"],
        "cid": view["cid"],
        "pages": [{"cid": p["cid"], "part": p["part"]} for p in view.get("pages", [])],
    }


def get_subtitles(bvid: str, cid: int, sessdata: str = None) -> list:
    """
    Fetch CC subtitles for a video.
    Returns list of subtitle entries with text + timestamps, or empty list.
    """
    headers = {"User-Agent": USER_AGENT, "Referer": "https://www.bilibili.com"}
    if sessdata:
        headers["Cookie"] = f"SESSDATA={sessdata}"

    resp = requests.get(
        f"{BILIBILI_API}/x/player/v2",
        params={"bvid": bvid, "cid": cid},
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    if data["code"] != 0:
        return []

    subtitle_info = data.get("data", {}).get("subtitle", {})
    subtitles = subtitle_info.get("subtitles", [])

    if not subtitles:
        return []

    # Prefer Chinese subtitles, fallback to first available
    sub_url = None
    for sub in subtitles:
        lang = sub.get("lan", "")
        url = sub.get("subtitle_url", "").strip()
        if not url:
            continue
        if lang in ("zh-CN", "zh-Hans", "ai-zh"):
            sub_url = url
            break
    if not sub_url:
        # Fallback: find any entry with a non-empty URL
        for sub in subtitles:
            url = sub.get("subtitle_url", "").strip()
            if url:
                sub_url = url
                break
    if not sub_url:
        return []

    # Ensure HTTPS
    if sub_url.startswith("//"):
        sub_url = "https:" + sub_url

    # Download subtitle JSON
    sub_resp = requests.get(sub_url, headers=headers, timeout=15)
    sub_resp.raise_for_status()
    sub_data = sub_resp.json()

    # B站字幕格式: {"body": [{"from": 0.0, "to": 2.5, "content": "text"}, ...]}
    body = sub_data.get("body", [])
    if not body:
        return []

    return body


def subtitle_to_text(subtitles: list, with_timestamps: bool = False) -> str:
    """Convert subtitle entries to plain text."""
    lines = []
    for entry in subtitles:
        text = entry.get("content", "").strip()
        if not text:
            continue
        if with_timestamps:
            ts = format_time(entry.get("from", 0))
            lines.append(f"[{ts}] {text}")
        else:
            lines.append(text)
    return "\n".join(lines)


def format_time(seconds: float) -> str:
    """Format seconds to MM:SS or HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def get_audio_url(bvid: str, cid: int, sessdata: str = None) -> str:
    """Get audio stream URL from Bilibili playback API."""
    headers = {"User-Agent": USER_AGENT, "Referer": "https://www.bilibili.com"}
    if sessdata:
        headers["Cookie"] = f"SESSDATA={sessdata}"

    resp = requests.get(
        f"{BILIBILI_API}/x/player/wbi/playurl",
        params={"bvid": bvid, "cid": cid, "fnval": 16},
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data["code"] != 0:
        raise RuntimeError(f"Playback API error: {data.get('message', data['code'])}")

    dash = data.get("data", {}).get("dash", {})
    audios = dash.get("audio", [])
    if not audios:
        # Fallback: try durl (flv/mp4 format)
        durls = data.get("data", {}).get("durl", [])
        if durls:
            return durls[0]["url"]
        raise RuntimeError("No audio streams found")

    # Pick highest quality audio
    audios.sort(key=lambda a: a.get("bandwidth", 0), reverse=True)
    return audios[0]["baseUrl"]


def download_audio(bvid: str, cid: int, output_dir: str, sessdata: str = None) -> str:
    """Download audio from Bilibili via playback API. Returns path to audio file."""
    audio_url = get_audio_url(bvid, cid, sessdata)

    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.bilibili.com",
    }
    if sessdata:
        headers["Cookie"] = f"SESSDATA={sessdata}"

    output_path = os.path.join(output_dir, f"{bvid}.m4a")

    resp = requests.get(audio_url, headers=headers, stream=True, timeout=60)
    resp.raise_for_status()

    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    if os.path.getsize(output_path) < 1024:
        raise RuntimeError("Downloaded audio file is too small (likely empty)")

    # Convert to mp3 for smaller size (ASR API has 10MB limit)
    mp3_path = os.path.join(output_dir, f"{bvid}.mp3")
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", output_path, "-ac", "1", "-ar", "16000", "-b:a", "48k", mp3_path],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode == 0 and os.path.exists(mp3_path):
        os.remove(output_path)
        return mp3_path

    # If ffmpeg fails, return the original file
    return output_path


def split_audio(audio_path: str, output_dir: str, chunk_duration: int = 300) -> list:
    """Split audio into chunks of chunk_duration seconds (default 5 min). Returns list of paths."""
    # Get total duration
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True, timeout=30,
    )
    total_duration = float(probe.stdout.strip())

    if total_duration <= chunk_duration:
        return [audio_path]

    chunks = []
    num_chunks = int(total_duration / chunk_duration) + 1
    for i in range(num_chunks):
        start = i * chunk_duration
        if start >= total_duration:
            break
        chunk_path = os.path.join(output_dir, f"chunk_{i:03d}.mp3")
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path, "-ss", str(start),
             "-t", str(chunk_duration), "-ac", "1", "-ar", "16000", "-b:a", "48k", chunk_path],
            capture_output=True, text=True, timeout=60,
        )
        if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 1024:
            chunks.append(chunk_path)

    return chunks if chunks else [audio_path]


def audio_to_base64(audio_path: str) -> str:
    """Read audio file and return base64 encoded data URL."""
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    # Check size (base64 limit ~10MB)
    b64 = base64.b64encode(audio_bytes).decode("utf-8")
    if len(b64) > 10 * 1024 * 1024:
        raise RuntimeError(
            f"Audio too large for ASR API ({len(b64) / 1024 / 1024:.1f}MB, limit 10MB). "
            "Try trimming or compressing the audio."
        )

    ext = os.path.splitext(audio_path)[1].lower()
    mime = "audio/mpeg" if ext == ".mp3" else "audio/wav"
    return f"data:{mime};base64,{b64}"


def transcribe_with_mimo_asr(audio_path: str) -> str:
    """Transcribe audio using MiMo-V2.5-ASR via Xiaomi API."""
    api_key = os.environ.get("XIAOMI_API_KEY") or os.environ.get("MIMO_API_KEY")
    if not api_key:
        raise RuntimeError(
            "No API key found. Set XIAOMI_API_KEY or MIMO_API_KEY environment variable."
        )

    base_url = os.environ.get(
        "XIAOMI_BASE_URL", "https://api.xiaomimimo.com/v1"
    ).rstrip("/")

    audio_data_url = audio_to_base64(audio_path)

    ext = os.path.splitext(audio_path)[1].lower()
    audio_format = "mp3" if ext == ".mp3" else "wav"

    payload = {
        "model": "mimo-v2.5-asr",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_data_url,
                            "format": audio_format,
                        },
                    }
                ],
            }
        ],
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    resp = requests.post(
        f"{base_url}/chat/completions",
        json=payload,
        headers=headers,
        timeout=120,
    )
    resp.raise_for_status()
    result = resp.json()

    # Extract text from response
    choices = result.get("choices", [])
    if not choices:
        raise RuntimeError(f"Empty ASR response: {json.dumps(result, ensure_ascii=False)}")

    text = choices[0].get("message", {}).get("content", "")
    if not text:
        raise RuntimeError(f"No text in ASR response: {json.dumps(result, ensure_ascii=False)}")

    return text


def main():
    parser = argparse.ArgumentParser(description="Bilibili video transcript extractor")
    parser.add_argument("url", help="Bilibili video URL or BV ID")
    parser.add_argument("--sessdata", help="Bilibili SESSDATA cookie (default: from BILIBILI_SESSDATA env var)")
    parser.add_argument(
        "--timestamps", action="store_true", help="Include timestamps in output"
    )
    parser.add_argument(
        "--text-only", action="store_true", help="Output plain text only (no JSON)"
    )
    parser.add_argument(
        "--force-asr", action="store_true", help="Skip subtitle check, force ASR"
    )
    parser.add_argument(
        "--asr-only", action="store_true", help="Only output ASR transcription (no subtitle check)"
    )
    args = parser.parse_args()

    try:
        bvid = parse_bvid(args.url)
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    # Auto-load SESSDATA from env if not provided via CLI
    if not args.sessdata:
        args.sessdata = os.environ.get("BILIBILI_SESSDATA")

    # Step 1: Get video info
    try:
        info = get_video_info(bvid, args.sessdata)
    except Exception as e:
        print(json.dumps({"error": f"Failed to get video info: {e}"}))
        sys.exit(1)

    result = {
        "bvid": bvid,
        "title": info["title"],
        "owner": info["owner"],
        "duration": info["duration"],
        "source": None,
        "text": None,
    }

    # Step 2: Try subtitles first (unless --force-asr or --asr-only)
    if not args.force_asr and not args.asr_only:
        try:
            subtitles = get_subtitles(bvid, info["cid"], args.sessdata)
            if subtitles:
                text = subtitle_to_text(subtitles, args.timestamps)
                result["source"] = "subtitle"
                result["text"] = text
                result["subtitle_count"] = len(subtitles)
        except Exception as e:
            # Subtitle fetch failed, will fall through to ASR
            print(f"# Subtitle fetch failed: {e}", file=sys.stderr)

    # Step 3: Fallback to ASR if no subtitles
    if result["text"] is None:
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                print(f"# Downloading audio for {bvid}...", file=sys.stderr)
                audio_path = download_audio(bvid, info["cid"], tmpdir, args.sessdata)

                # Check file size — if >7MB (base64 ~10MB), split into chunks
                file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
                if file_size_mb > 7:
                    print(f"# Audio {file_size_mb:.1f}MB, splitting into chunks...", file=sys.stderr)
                    chunks = split_audio(audio_path, tmpdir)
                    texts = []
                    for i, chunk_path in enumerate(chunks):
                        print(f"# Transcribing chunk {i+1}/{len(chunks)}...", file=sys.stderr)
                        chunk_text = transcribe_with_mimo_asr(chunk_path)
                        texts.append(chunk_text)
                    text = "\n".join(texts)
                else:
                    print(f"# Transcribing with MiMo-V2.5-ASR...", file=sys.stderr)
                    text = transcribe_with_mimo_asr(audio_path)

                result["source"] = "asr"
                result["text"] = text
        except Exception as e:
            result["error"] = f"ASR failed: {e}"

    # Output
    if args.text_only:
        if result["text"]:
            print(result["text"])
        elif result.get("error"):
            print(f"ERROR: {result['error']}", file=sys.stderr)
            sys.exit(1)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
