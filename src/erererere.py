# gestix_mediapipe2.py
# ─────────────────────────────────────────────────────────
# MediaPipe + OpenCV 的手勢偵測執行緒，提供：
#   - Config：全域設定（含手勢對應表）
#   - SharedState：與遊戲主迴圈共享的手勢 / 執行旗標
#   - camera_thread(shared)：開相機、辨識手勢、寫入 shared
#
# 手勢名稱（供遊戲使用）：
#   "Fist", "Open", "Point1", "Gun", "ThumbUp", "Victory", "OK", "DualOpen", "NONE"
#
# 依賴套件：mediapipe, opencv-python
# pip install mediapipe==0.10.9 opencv-python
# ─────────────────────────────────────────────────────────
from __future__ import annotations
import cv2
import time
import math
from collections import deque, Counter
from threading import Lock
from typing import Optional, Tuple

try:
    import mediapipe as mp
except Exception as e:
    mp = None

# =========================
# 設定
# =========================
class Config:
    # 螢幕與節奏
    SCREEN_W = 960
    SCREEN_H = 540
    GAME_FPS = 60

    # 遊戲物理
    SCROLL_SPEED = 5
    GRAVITY = 1.04
    JUMP_VELOCITY = -17
    GROUND_H = 56

    # 射彈
    BULLET_SPEED = 16

    # 顏色（僅供 UI 參考）
    COLOR_SKY_TOP = (10, 15, 25)
    COLOR_SKY_BOT = (30, 40, 60)
    COLOR_GROUND = (20, 20, 25)
    COLOR_TEXT = (230, 230, 230)
    COLOR_BULLET = (255, 160, 60)

    # 能量 / 護盾（DualOpen）
    ULTI_DURATION = 10.0
    COIN_ENERGY_GAIN = 10

    # 苦無掉落與冷卻
    KUNAI_SPAWN_TIME = 5.0   # ← 想更快就改小
    KUNAI_COOLDOWN = 0.5
    KUNAI_MAX_STACK = 10

    # 生成安全距離
    SAFE_H_DIST = 110
    SAFE_V_DIST = 80
    SAFE_EUCL   = 150

    # 玩家血量
    MAX_HP = 100

    # 手勢對動作對應（遊戲會用這個表）
    GESTURE_MAPPING = {
        "Fist": "START_GAME",
        "Open": "JUMP",
        "Point1": "PAUSE_TOGGLE",
        "Gun": "SHOOT",       # 遊戲端已固定為丟苦無
        "ThumbUp": "RESTART",
        "Victory": "JUMP",
        "OK": "NONE",
        "DualOpen": "ULTI",
        "NONE": "NONE",
    }

# =========================
# 共用狀態
# =========================
class SharedState:
    def __init__(self):
        self._lock = Lock()
        self._running = True
        self._gesture = "NONE"
        self._last_update_ts = 0.0

    # 遊戲主迴圈會查
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def set_running(self, v: bool):
        with self._lock:
            self._running = v

    # 相機執行緒寫入 / 主程式讀出
    def set_gesture(self, g: str):
        with self._lock:
            self._gesture = g
            self._last_update_ts = time.time()

    def get_gesture(self) -> str:
        with self._lock:
            g = self._gesture
            ts = self._last_update_ts
        # 若超過一定時間沒更新，回退 NONE（避免殘留手勢）
        if time.time() - ts > 0.6:
            return "NONE"
        return g

# =========================
# 手勢判斷工具
# =========================
# MediaPipe Hands 標記點索引
TIP_IDS = [4, 8, 12, 16, 20]  # 拇指至小指
MCP_IDS = [2, 5, 9, 13, 17]   # 指根

def _is_thumb_up(landmarks, handness_label: str) -> bool:
    # 以 x 方向判斷拇指伸直（左右手鏡像）
    # landmarks: 21 點 (x,y)
    if handness_label == "Left":
        return landmarks[4][0] < landmarks[3][0] < landmarks[2][0]
    else:
        return landmarks[4][0] > landmarks[3][0] > landmarks[2][0]

def _is_finger_up(landmarks, tip_id: int, mcp_id: int) -> bool:
    # y 越小代表越上方；tip 在 mcp 上方視為「伸直」
    return landmarks[tip_id][1] < landmarks[mcp_id][1] - 0.02

def _pinch_ok(landmarks) -> bool:
    # 判斷 OK：拇指與食指距離很近
    x1, y1 = landmarks[4]
    x2, y2 = landmarks[8]
    d = math.hypot(x1 - x2, y1 - y2)
    return d < 0.05

def _classify_single_hand(landmarks, label: str) -> str:
    # landmarks: list[(x,y)] 正規化至 [0,1]
    thumb = _is_thumb_up(landmarks, label)
    idx   = _is_finger_up(landmarks, 8, 5)
    mid   = _is_finger_up(landmarks,12, 9)
    ring  = _is_finger_up(landmarks,16,13)
    pinky = _is_finger_up(landmarks,20,17)

    # OK
    if _pinch_ok(landmarks) and (mid or ring or pinky):
        return "OK"

    # Victory
    if idx and mid and not ring and not pinky:
        return "Victory"

    # Point1
    if idx and not mid and not ring and not pinky and not thumb:
        return "Point1"

    # Gun（食指+拇指）
    if idx and thumb and not mid and not ring and not pinky:
        return "Gun"

    # ThumbUp（只有拇指）
    if thumb and not idx and not mid and not ring and not pinky:
        return "ThumbUp"

    # Open（五指張開）
    if thumb and idx and mid and ring and pinky:
        return "Open"

    # Fist（皆收）
    if not thumb and not idx and not mid and not ring and not pinky:
        return "Fist"

    return "NONE"

def _smooth_majority(buffer: deque[str], k: int = 5) -> str:
    if not buffer:
        return "NONE"
    c = Counter(list(buffer)[-k:])
    return c.most_common(1)[0][0]

# =========================
# 相機執行緒
# =========================
def camera_thread(shared: SharedState, show_debug: bool = True, cam_index: int = 0):
    """
    讀取相機並以 MediaPipe Hands 辨識單/雙手手勢，將結果寫入 shared。
    - DualOpen：同時偵測到兩手皆 "Open"
    - 若無畫面更新一段時間，shared.get_gesture() 會自動回 "NONE"
    - 按下 'q' 可關閉相機並結束（也會 set_running(False)）
    """
    if mp is None:
        # 沒有 mediapipe 就直接回傳，避免整個程式當掉
        print("[gestix_mediapipe2] mediapipe 未安裝，手勢固定為 NONE。")
        while shared.is_running():
            time.sleep(0.05)
        return

    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=2,
        model_complexity=1,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    cap = cv2.VideoCapture(cam_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  960)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)

    # 手勢平滑
    gesture_buf = deque(maxlen=7)
    last_gesture = "NONE"
    last_update = time.time()

    try:
        while shared.is_running():
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.02)
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = hands.process(rgb)

            single_labels = []
            lm_by_hand = []  # 每隻手的 21 點 (x,y)
            if res.multi_hand_landmarks:
                h, w = frame.shape[:2]
                # 取得每隻手的左右標籤
                hand_labels = []
                if res.multi_handedness:
                    for c in res.multi_handedness:
                        hand_labels.append(c.classification[0].label)  # "Left" or "Right"
                else:
                    hand_labels = ["Right"] * len(res.multi_hand_landmarks)

                for lm, label in zip(res.multi_hand_landmarks, hand_labels):
                    pts = [(p.x, p.y) for p in lm.landmark]
                    lm_by_hand.append(pts)
                    g = _classify_single_hand(pts, label)
                    single_labels.append(g)

            # 雙手皆 Open => DualOpen 優先
            if len(single_labels) >= 2 and single_labels.count("Open") >= 2:
                cur = "DualOpen"
            else:
                # 任選第一個非 NONE 的手勢
                cur = "NONE"
                for g in single_labels:
                    if g != "NONE":
                        cur = g
                        break

            gesture_buf.append(cur)
            smoothed = _smooth_majority(gesture_buf)

            # 僅在手勢有變化或經過一段時間時寫回 shared，降低 jitter
            if smoothed != last_gesture or (time.time() - last_update) > 0.25:
                shared.set_gesture(smoothed)
                last_gesture = smoothed
                last_update = time.time()

            if show_debug:
                # 簡易除錯視窗（左上角顯示手勢）
                txt = f"Gesture: {smoothed}"
                cv2.putText(frame, txt, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 240, 255), 2, cv2.LINE_AA)
                cv2.imshow("GestiX — Camera", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:  # q 或 ESC
                    shared.set_running(False)

    finally:
        try:
            hands.close()
        except Exception:
            pass
        cap.release()
        if show_debug:
            cv2.destroyAllWindows()

# 單檔測試：顯示即時手勢字樣
if __name__ == "__main__":
    shared = SharedState()
    try:
        camera_thread(shared, show_debug=True, cam_index=0)
    except KeyboardInterrupt:
        shared.set_running(False)
