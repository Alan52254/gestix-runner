# gestix_mediapipe.py
# MediaPipe gesture module for GestiX Dino+
# - Gestures: Fist(START), Open(JUMP), Point1(PAUSE/RESUME), Gun(SHOOT), ThumbUp(RESTART), DualOpen(ULTI)
# - Right-hand priority, N-frame voting, trigger cooldown
# - Debug camera window with green skeleton

import time
import math
import threading
from collections import deque

import cv2
import numpy as np
import mediapipe as mp


# =========================
# 1) Configuration (shared with runner)
# =========================
class Config:
    # Camera
    CAM_INDEX = 0
    CAM_W, CAM_H = 640, 360

    # Game window (runner 會使用)
    SCREEN_W, SCREEN_H = 1280, 720
    GAME_FPS = 60
    SCROLL_SPEED = 5

    # Physics for runner
    GRAVITY = 1.1
    JUMP_VELOCITY = -20

    # Sizes (runner assets)
    PLAYER_W, PLAYER_H = 120, 150
    COIN_W, COIN_H = 36, 36
    GUN_W, GUN_H = 60, 32
    STAR_W, STAR_H = 86, 86
    BULLET_SPEED = 16
    GROUND_H = 56

    # Colors (runner HUD/scene)
    COLOR_SKY = (170, 220, 245)
    COLOR_GROUND = (140, 250, 25)
    COLOR_TEXT = (20, 20, 20)
    COLOR_BULLET = (255, 140, 0)

    # Background removal tolerance for runner (not used here)
    BG_REMOVE_TOLERANCE = 45

    # Gesture voting & debounce
    MAX_HANDS = 2
    VOTE_FRAMES = 3
    TRIGGER_COOLDOWN = 0.12

    # Gesture mapping (runner 會以此解析)
    GESTURE_MAPPING = {
        "Fist": "START_GAME",
        "Open": "JUMP",
        "Gun": "SHOOT",
        "OK": "SPEED_UP",        # 保留；runner 目前可能不用
        "Victory": "ULTI",       # 保留；runner 目前可能不用
        "ThumbUp": "RESTART",
        "Point1": "PAUSE_TOGGLE",   # 這版用「比1」取代 Wave
        "DualOpen": "ULTI",      # 保留；雙手張開
    }
    CONSUME_GESTURES = {"Open", "Gun", "OK", "Victory", "ThumbUp", "DualOpen", "Point1"}


# =========================
# 2) Shared State
# =========================
class SharedState:
    def __init__(self):
        self._lock = threading.Lock()
        self._running = True
        self._gesture = "None"
        self._gesture_ts = 0.0
        self._camera_view = None
        self._recognizer_ref = None

    def set_running(self, val: bool):
        with self._lock:
            self._running = val

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def set_gesture(self, gesture: str):
        # 帶冷卻，避免抖動觸發
        with self._lock:
            now = time.time()
            if gesture != "None":
                if gesture != self._gesture or (now - self._gesture_ts) >= Config.TRIGGER_COOLDOWN:
                    self._gesture = gesture
                    self._gesture_ts = now

    def get_gesture(self) -> str:
        with self._lock:
            g = self._gesture
            if g in Config.CONSUME_GESTURES:
                self._gesture = "None"
            return g

    def set_camera_view(self, frame, fps, raw_gestures):
        with self._lock:
            self._camera_view = {
                "frame": frame.copy(),
                "fps": fps,
                "raw_gestures": dict(raw_gestures),
            }

    def get_camera_view(self):
        with self._lock:
            return self._camera_view.copy() if self._camera_view else None

    def set_recognizer_ref(self, recognizer):
        with self._lock:
            self._recognizer_ref = recognizer

    def get_recognizer_ref(self):
        with self._lock:
            return self._recognizer_ref


# =========================
# 3) Gesture Recognizer
# =========================
class HandGestureRecognizer:
    def __init__(self):
        self.mp_hands = mp.solutions.hands
        self.mp_draw = mp.solutions.drawing_utils
        self.mp_styles = mp.solutions.drawing_styles

        self.hands = self.mp_hands.Hands(
            max_num_hands=Config.MAX_HANDS,
            model_complexity=0,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6
        )

        self.tip_ids = [4, 8, 12, 16, 20]
        self.vote = deque(maxlen=Config.VOTE_FRAMES)

    @staticmethod
    def _dist2d(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def _get_finger_status(self, lms, handedness: str):
        """
        回傳 [thumb, index, middle, ring, pinky] 是否伸直 (1/0)
        """
        fingers = [0] * 5
        # Thumb 橫向判斷
        if handedness == "Right":
            fingers[0] = 1 if lms[self.tip_ids[0]].x < lms[self.tip_ids[0] - 1].x else 0
        else:  # Left
            fingers[0] = 1 if lms[self.tip_ids[0]].x > lms[self.tip_ids[0] - 1].x else 0
        # 其餘四指：tip 高於 PIP 視為伸直
        for i in range(1, 5):
            fingers[i] = 1 if lms[self.tip_ids[i]].y < lms[self.tip_ids[i] - 2].y else 0
        return fingers

    def _is_gun(self, fingers):
        # 食指伸出，其他(中環小)收起；拇指可自由
        return fingers[1] == 1 and (fingers[2] + fingers[3] + fingers[4]) == 0

    def _is_ok(self, lms, handedness):
        base = self._dist2d((lms[0].x, lms[0].y), (lms[9].x, lms[9].y)) + 1e-6
        d48 = self._dist2d((lms[4].x, lms[4].y), (lms[8].x, lms[8].y)) / base
        fingers = self._get_finger_status(lms, handedness)
        return d48 < 0.35 and fingers[1] == 1 and sum(fingers[2:]) <= 1

    def _is_victory(self, fingers):
        return fingers[1] == 1 and fingers[2] == 1 and fingers[3] == 0 and fingers[4] == 0

    def _is_point1(self, fingers):
        """
        比 1：只有食指伸直，其它四指收起（允許拇指半開，容忍度稍微放寬）
        """
        return fingers[1] == 1 and fingers[2] == 0 and fingers[3] == 0 and fingers[4] == 0

    def _single_hand_gesture(self, lms, handedness: str):
        fingers = self._get_finger_status(lms, handedness)
        if self._is_ok(lms, handedness):  return "OK"
        if self._is_victory(fingers):     return "Victory"
        if self._is_gun(fingers):         return "Gun"
        if self._is_point1(fingers):      return "Point1"
        if fingers == [1, 0, 0, 0, 0]:    return "ThumbUp"
        if fingers == [0, 0, 0, 0, 0]:    return "Fist"
        if fingers == [1, 1, 1, 1, 1]:    return "Open"
        return "None"

    def recognize(self, frame_rgb):
        res = self.hands.process(frame_rgb)
        raw_g = {"Left": "None", "Right": "None"}
        final_gesture = "None"
        draw_lms = res.multi_hand_landmarks if res.multi_hand_landmarks else []

        if res.multi_hand_landmarks:
            # 右手優先
            lr = []
            for i, hand_lms in enumerate(res.multi_hand_landmarks):
                handed = res.multi_handedness[i].classification[0].label  # 'Left'/'Right'
                lr.append((handed, hand_lms))

            # 依 Right 優先排序
            lr.sort(key=lambda x: 0 if x[0] == "Right" else 1)

            for handed, hand_lms in lr:
                g = self._single_hand_gesture(hand_lms.landmark, handed)
                raw_g[handed] = g

            # 雙手張開 -> DualOpen
            if raw_g["Left"] == "Open" and raw_g["Right"] == "Open":
                final_gesture = "DualOpen"
            else:
                # 右手優先
                final_gesture = raw_g["Right"] if raw_g["Right"] != "None" else raw_g["Left"]

        # 投票穩定
        self.vote.append(final_gesture)
        voted = max(set(self.vote), key=self.vote.count) if self.vote else "None"
        return voted, raw_g, draw_lms

    def draw_landmarks(self, bgr_frame, lms_list):
        if not lms_list:
            return bgr_frame
        for hand_lms in lms_list:
            self.mp_draw.draw_landmarks(
                bgr_frame,
                hand_lms,
                self.mp_hands.HAND_CONNECTIONS,
                self.mp_styles.get_default_hand_landmarks_style(),
                self.mp_styles.get_default_hand_connections_style(),
            )
        return bgr_frame

    def close(self):
        self.hands.close()


# =========================
# 4) Camera Thread
# =========================
def camera_thread(shared: SharedState):
    recog = HandGestureRecognizer()
    shared.set_recognizer_ref(recog)

    cap = cv2.VideoCapture(Config.CAM_INDEX)
    if not cap.isOpened():
        print(f"[Camera] Cannot open camera index {Config.CAM_INDEX}")
        shared.set_running(False)
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, Config.CAM_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.CAM_H)

    t0, cnt, fps_disp = time.time(), 0, 0.0

    try:
        while shared.is_running():
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.02)
                continue

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            voted, raw, draw_lms = recog.recognize(rgb)
            shared.set_gesture(voted)

            # Debug overlay
            dbg = frame.copy()
            dbg = recog.draw_landmarks(dbg, draw_lms)

            cnt += 1
            now = time.time()
            if now - t0 >= 1.0:
                fps_disp = cnt / (now - t0)
                cnt, t0 = 0, now

            # Text overlays
            txt_l = f"L:{raw.get('Left','None')}"
            txt_r = f"R:{raw.get('Right','None')}"
            cv2.putText(dbg, f"CamFPS:{fps_disp:.1f}", (8, 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)
            cv2.putText(dbg, txt_l, (8, 34),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 1, cv2.LINE_AA)
            cv2.putText(dbg, txt_r, (72, 34),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 0, 255), 1, cv2.LINE_AA)

            shared.set_camera_view(dbg, fps_disp, raw)

            # === Debug window (green skeleton) ===
            small = cv2.resize(dbg, (320, 180))
            cv2.imshow("GestiX Camera (Debug)", small)
            # ESC 直接關閉整個系統
            if cv2.waitKey(1) & 0xFF == 27:
                shared.set_running(False)
                break

    except Exception as e:
        print(f"[Camera] Unexpected error: {e}")
    finally:
        cap.release()
        recog.close()
        cv2.destroyAllWindows()


# =========================
# 5) Standalone debug run
# =========================
if __name__ == "__main__":
    # 獨立測試：只跑攝影機+手勢偵測與視窗
    shared = SharedState()
    th = threading.Thread(target=camera_thread, args=(shared,), daemon=True)
    th.start()
    print("Running MediaPipe module... (Press ESC in camera window to exit)")

    # 小型輪詢直到 camera_thread 關閉
    try:
        while shared.is_running():
            time.sleep(0.05)
    except KeyboardInterrupt:
        shared.set_running(False)

    th.join()
    print("MediaPipe module closed.")
