# GestiX Runner — Gesture Experience Game (MVP)

用 **MediaPipe Hands + OpenCV** 即時辨識 **Wave / Open / Fist / ThumbUp** 四種手勢，透過 **PyGame** 操控 2D 跑酷遊戲。目標：在一般筆電上達成 **FPS ≥ 25**、**Latency < 150ms** 的可展示 MVP。

## ✨ Features
- 即時手勢辨識（單手）：揮手、張開、握拳、比讚
- 去抖動（滑動投票 + 冷卻機制），降低誤觸發
- 2D 跑酷：跳躍、滑行、障礙、分數與暫停
- 針對新手的單檔 MVP（`src/gestix_runner.py`），本機即可跑

## 🧰 Tech Stack
- Python 3.10
- MediaPipe Hands, OpenCV, PyGame (pygame-ce), NumPy

## 📦 Install (Windows/macOS/Linux)
> 建議使用 Python 3.10 + 64-bit。本機執行，**Colab 不建議**（相機權限不穩）。

### 使用 uv（推薦）
```bash
# 建立與啟用虛擬環境
uv venv .venv -p 3.10
# Windows
.\.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate

# 安裝套件
uv pip install --upgrade pip
uv pip install -r requirements.txt --default-timeout 60
