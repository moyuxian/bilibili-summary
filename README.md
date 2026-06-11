# bilibili-summary

B站视频总结工具：优先使用 CC 字幕，无字幕时自动调用 MiMo-V2.5-ASR 进行语音识别，最终由 LLM 生成摘要。

## 工作流程

```
B站视频链接
    │
    ▼
解析 BV 号 → 获取视频信息（标题、UP主、时长）
    │
    ▼
尝试获取 CC 字幕
    │
    ├── 有字幕 → 直接使用字幕文本 ✅
    │
    └── 无字幕 → 下载音频流 → 自动分片 → MiMo-V2.5-ASR 转写
                    │
                    ▼
              得到完整文本
    │
    ▼
LLM 生成总结
```

## 功能特点

- **字幕优先**：通过 B站 API 自动获取 AI 生成的 CC 字幕，速度快、质量高
- **ASR 兜底**：无字幕时自动下载音频，调用小米 MiMo-V2.5-ASR 模型转写
- **长视频支持**：音频自动按 5 分钟切片，逐段转写后拼接，不受 API 大小限制
- **双语识别**：中文、英文、中英混读均可识别
- **零依赖外部工具**：不依赖 yt-dlp，直接通过 B站 API 下载音频流

## 环境要求

- Python 3.8+
- `requests` 库
- `ffmpeg`（音频转码用）

```bash
pip install requests
sudo apt install ffmpeg   # Ubuntu/Debian
brew install ffmpeg       # macOS
```

## 环境变量配置

在 `~/.hermes/.env` 或 shell 中设置：

```bash
# 小米 MiMo API（ASR 转写必需）
XIAOMI_API_KEY=你的API密钥
XIAOMI_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1

# B站 SESSDATA（可选，但强烈推荐，有它才能拿到大部分字幕）
BILIBILI_SESSDATA=你的SESSDATA值
```

### 如何获取 SESSDATA

1. 浏览器登录 bilibili.com
2. 按 F12 打开开发者工具
3. `Application` → `Cookies` → `https://www.bilibili.com`
4. 找到 `SESSDATA`，复制值
5. 有效期约几个月，失效后重新获取即可

### 如何获取小米 API Key

1. 注册 [小米 MiMo 开放平台](https://platform.xiaomimimo.com)
2. 开通 Token Plan
3. 在控制台获取 API Key

## 使用方法

```bash
# 基础用法（JSON 格式输出）
python3 scripts/bilibili_summary.py "https://www.bilibili.com/video/BV1xx411c7XW"

# 纯文本输出（适合喂给 LLM 做总结）
python3 scripts/bilibili_summary.py "URL" --text-only

# 带时间戳
python3 scripts/bilibili_summary.py "URL" --text-only --timestamps

# 强制走 ASR（跳过字幕检查）
python3 scripts/bilibili_summary.py "URL" --force-asr

# 手动指定 SESSDATA
python3 scripts/bilibili_summary.py "URL" --sessdata "你的SESSDATA"
```

### 输出格式

JSON 输出示例：

```json
{
  "bvid": "BV1xx411c7XW",
  "title": "视频标题",
  "owner": "UP主名称",
  "duration": 600,
  "source": "subtitle",
  "text": "完整字幕/转录文本...",
  "subtitle_count": 42
}
```

`source` 字段标识文本来源：`subtitle`（CC 字幕）或 `asr`（语音识别）。

## 技术细节

| 环节 | 实现方式 |
|------|---------|
| 视频信息 | B站 `/x/web-interface/view` API |
| 字幕获取 | B站 `/x/player/v2` API → `aisubtitle.hdslb.com` |
| 音频下载 | B站 `/x/player/wbi/playurl` API（DASH 音频流） |
| 音频转码 | ffmpeg → 单声道 16kHz 48kbps MP3 |
| 长音频切片 | ffmpeg 按 5 分钟切割 |
| 语音识别 | 小米 MiMo-V2.5-ASR（OpenAI 兼容 API） |

## 适用场景

- 快速了解长视频内容，不用从头看到尾
- 视频内容检索和归档
- 为 AI 对话提供视频上下文
- 配合 Hermes Agent 使用（作为 skill 自动加载）

## 已知限制

- B站字幕 API 未登录时大部分视频拿不到字幕，建议配置 SESSDATA
- ASR API 单次请求 base64 上限约 10MB，超长视频（1h+）需要更多分片和 API 调用
- 部分需要大会员的视频可能无法获取音频流
- ASR 转写需要调用小米 API，会产生 token 消耗

## 许可证

MIT
