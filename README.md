# bilibili-summary

Bilibili video summarizer: fetch CC subtitles or fall back to MiMo-V2.5-ASR transcription, then summarize with LLM.

## Features

- **Subtitle-first**: automatically fetches CC subtitles from Bilibili API
- **ASR fallback**: if no subtitles, downloads audio and transcribes with MiMo-V2.5-ASR
- **Long audio support**: auto-splits long videos into 5-min chunks
- **Bilingual**: works with Chinese, English, and mixed-language content

## Setup

```bash
pip install requests
# ffmpeg required for audio processing
sudo apt install ffmpeg  # or: brew install ffmpeg
```

### Environment Variables

Set in `~/.hermes/.env` or your shell:

```bash
XIAOMI_API_KEY=your_xiaomi_api_key
XIAOMI_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
BILIBILI_SESSDATA=your_sessdata_cookie  # optional but recommended
```

## Usage

```bash
# Basic (JSON output)
python3 scripts/bilibili_summary.py "https://www.bilibili.com/video/BV1xx411c7XW"

# Plain text for LLM processing
python3 scripts/bilibili_summary.py "URL" --text-only

# With timestamps
python3 scripts/bilibili_summary.py "URL" --text-only --timestamps

# Force ASR (skip subtitle check)
python3 scripts/bilibili_summary.py "URL" --force-asr

# With SESSDATA cookie
python3 scripts/bilibili_summary.py "URL" --sessdata "your_sessdata"
```

## How It Works

```
B站链接 → 解析 BV ID → 获取视频信息
  ├── 有 CC 字幕 → 直接使用字幕文本
  └── 无字幕 → 下载音频 → 分片(如果太长) → MiMo-V2.5-ASR 转写
         ↓
      LLM 总结
```

## Requirements

- Python 3.8+
- `requests` library
- `ffmpeg` (for audio conversion)
- Xiaomi MiMo API key (for ASR fallback)
- Bilibili SESSDATA cookie (optional, for better subtitle access)

## License

MIT
