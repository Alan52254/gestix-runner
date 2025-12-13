# gestix_mediapipe2.py
# MediaPipe gesture module for GestiX Runner — Ninja Ink (Kunai-only version)
# - 提供 SharedState / Config / camera_thread，給 gestix_runner2.py & boss_room 使用
# - 手勢：
#   Fist      → START_GAME
#   Open      → JUMP
#   Point1    → PAUSE_TOGGLE
#   Gun       → SHOOT  （runner2 會把「槍」動作解讀成丟苦無）
#   ThumbUp   → RESTART
#   Victory   → JUMP
#   DualOpen  → ULTI（護盾）
#   OK        → NONE（保留，但不做遊戲動作）
#
# - 右手優先、N 幀投票、觸發冷卻
# - Debug 相機視窗 + 骨架
# - 可輸出 landmarks (21 x (x,y,z)) 供驗證/分析

import time
import math
import threading
from collections import deque

import cv2
import numpy as np
import mediapipe as mp


# =========================
# 1) Configuration
# =========================
class Config:
    # ---------- Camera ----------
    CAM_INDEX = 0
    CAM_W, CAM_H = 640, 360

    # ---------- Runner / 遊戲核心設定（對齊 gestix_runner2.py 的預設） ----------
    # 若之後在 runner2 裡改過 _ensure_config_defaults，記得這裡一起調整或乾脆移除讓 runner2 來填預設

    SCREEN_W = 960
    SCREEN_H = 540
    GAME_FPS = 60
    SCROLL_SPEED = 5

    GRAVITY = 1.04
    JUMP_VELOCITY = -17
    GROUND_H = 56
    BULLET_SPEED = 16

    # 視覺色彩（天空漸層 + 地面 + HUD）
    COLOR_SKY_TOP = (10, 15, 25)
    COLOR_SKY_BOT = (30, 40, 60)
    COLOR_GROUND = (20, 20, 25)
    COLOR_TEXT = (230, 230, 230)
    COLOR_BULLET = (255, 160, 60)

    # 護盾 / 查克拉
    ULTI_DURATION = 10.0
    COIN_ENERGY_GAIN = 10

    # 苦無相關
    KUNAI_SPAWN_TIME = 5.0    # 原世界拾取物生成間隔（秒）
    KUNAI_COOLDOWN = 0.5      # 丟苦無冷卻（秒）
    KUNAI_MAX_STACK = 10      # 苦無上限（HUD 顯示）

    # 生成物安全距離
    SAFE_H_DIST = 110
    SAFE_V_DIST = 80
    SAFE_EUCL = 150

    # 玩家 HP 上限
    MAX_HP = 100

    # 舊版 runner 可能用到的尺寸（目前 gestix_runner2 自己畫 player，不太會用到，但保留不影響）
    PLAYER_W, PLAYER_H = 58, 116
    COIN_W, COIN_H = 30, 30

    # ---------- Gesture voting & debounce ----------
    MAX_HANDS = 2
    VOTE_FRAMES = 2           # 越小反應越快，越大越穩定
    TRIGGER_COOLDOWN = 0.12   # 手勢觸發冷卻（秒）

    # ---------- Gesture → Action mapping（跟 gestix_runner2 的預設完全一樣） ----------
    GESTURE_MAPPING = {
        "Fist": "START_GAME",
        "Open": "JUMP",
        "Point1": "PAUSE_TOGGLE",
        "Gun": "SHOOT",
        "ThumbUp": "RESTART",
        "Victory": "JUMP",
        "OK": "NONE",
        "DualOpen": "ULTI",
    }

    # 這些手勢被讀一次後就會「消耗」，避免連續觸發（Fist 保持不消耗，當作狀態）
    CONSUME_GESTURES = {
        "Open",
        "Gun",
        "OK",
        "Victory",
        "ThumbUp",
        "DualOpen",
        "Point1",
    }


# =========================
# 2) Shared State
# =========================
class SharedState:
    """
    遊戲主進程與相機執行緒之間的溝通橋樑：
    - gesture：目前投票後的手勢（帶冷卻 / 一些會被「讀一次就清空」）
    - camera_view：最新 debug 影像 & FPS & 每手 raw 手勢 & landmarks
    - recognizer_ref：方便外部拿到 HandGestureRecognizer 物件做校正測試
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._running = True
        self._gesture = "None"
        self._gesture_ts = 0.0
        self._camera_view = None
        self._recognizer_ref = None

    # lifecycle
    def set_running(self, val: bool):
        with self._lock:
            self._running = val

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    # gesture with cooldown & consume-on-read
    def set_gesture(self, gesture: str):
        """
        由 camera_thread 呼叫，用來更新「目前投票後的手勢」。
        有做簡單冷卻：同一個手勢太頻繁出現不會一直覆蓋時間戳。
        """
        with self._lock:
            now = time.time()
            if gesture != "None":
                if gesture != self._gesture or (now - self._gesture_ts) >= Config.TRIGGER_COOLDOWN:
                    self._gesture = gesture
                    self._gesture_ts = now

    def get_gesture(self) -> str:
        """
        遊戲主迴圈用：
        - 回傳目前的手勢名稱（e.g. "Open", "Fist"...）
        - 若手勢在 CONSUME_GESTURES 裡，讀一次就清成 "None"
        """
        with self._lock:
            g = self._gesture
            if g in Config.CONSUME_GESTURES:
                self._gesture = "None"
            return g

    # camera frame bundle
    def set_camera_view(self, frame, fps, raw_gestures, landmarks_data=None):
        """
        存一份 debug 畫面 + FPS + 每手 raw 手勢 + landmarks
        給外部（例如 debug overlay HUD）存取
        """
        with self._lock:
            self._camera_view = {
                "frame": frame.copy(),
                "fps": fps,
                "raw_gestures": dict(raw_gestures),
                # List[{"handedness": str, "landmarks": [(x,y,z), ...]}]
                "landmarks": landmarks_data,
            }

    def get_camera_view(self):
        with self._lock:
            return self._camera_view.copy() if self._camera_view else None

    # recognizer reference (for HUD / validation)
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
            min_tracking_confidence=0.6,
        )

        self.tip_ids = [4, 8, 12, 16, 20]
        self.vote = deque(maxlen=Config.VOTE_FRAMES)

        # validation window（例如：20 幀裡面有幾幀是預期手勢）
        self.accuracy_win = deque(maxlen=20)
        self.expected_for_eval = None

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
        else:
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
        # ✌：食指 + 中指
        return fingers[1] == 1 and fingers[2] == 1 and fingers[3] == 0 and fingers[4] == 0

    def _is_point1(self, fingers):
        """
        比 1：只有食指伸直，其它四指收起（允許拇指半開）
        """
        return fingers[1] == 1 and fingers[2] == 0 and fingers[3] == 0 and fingers[4] == 0

    def _single_hand_gesture(self, lms, handedness: str):
        fingers = self._get_finger_status(lms, handedness)

        if self._is_ok(lms, handedness):
            return "OK"
        if self._is_victory(fingers):
            return "Victory"
        if self._is_gun(fingers):
            return "Gun"
        if self._is_point1(fingers):
            return "Point1"
        if fingers == [1, 0, 0, 0, 0]:
            return "ThumbUp"
        if fingers == [0, 0, 0, 0, 0]:
            return "Fist"
        if fingers == [1, 1, 1, 1, 1]:
            return "Open"
        return "None"

    def recognize(self, frame_rgb):
        """
        輸入：RGB frame
        回傳：
          voted_gesture: 經過 N 幀投票後的最終手勢（"Fist"/"Open"/"None"...）
          raw_gestures:  每隻手各自的手勢 {'Left': 'Open', 'Right': 'Gun'}
          draw_lms:      mediapipe 的 landmarks 物件，用來畫在相機畫面上
          landmarks_data: 乾淨的數值版 landmark，給分析/儲存用
        """
        res = self.hands.process(frame_rgb)
        raw_g = {"Left": "None", "Right": "None"}
        final_gesture = "None"
        draw_lms = res.multi_hand_landmarks if res.multi_hand_landmarks else []
        landmarks_data = None

        if res.multi_hand_landmarks:
            landmarks_data = []
            lr = []
            for i, hand_lms in enumerate(res.multi_hand_landmarks):
                handed = res.multi_handedness[i].classification[0].label  # 'Left'/'Right'
                lr.append((handed, hand_lms))

            # 右手優先排序
            lr.sort(key=lambda x: 0 if x[0] == "Right" else 1)

            for handed, hand_lms in lr:
                g = self._single_hand_gesture(hand_lms.landmark, handed)
                raw_g[handed] = g

                pts = [(lm.x, lm.y, lm.z) for lm in hand_lms.landmark]
                landmarks_data.append({"handedness": handed, "landmarks": pts})

            # 雙手張開 -> DualOpen
            if raw_g["Left"] == "Open" and raw_g["Right"] == "Open":
                final_gesture = "DualOpen"
            else:
                final_gesture = raw_g["Right"] if raw_g["Right"] != "None" else raw_g["Left"]

        # 投票（穩定手勢）
        self.vote.append(final_gesture)
        voted = max(set(self.vote), key=self.vote.count) if self.vote else "None"
        self.accuracy_win.append(voted)
        # Validation window（若有設定 expected_for_eval，就計算準確率）
        # if self.expected_for_eval is not None:
        #     self.accuracy_win.append(1 if voted == self.expected_for_eval else 0)

        return voted, raw_g, draw_lms, landmarks_data

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

    # Validation API（例如要測「Victory」連續 20 幀正確幾幀）
    def set_expected_for_eval(self, gesture_name_or_none):
        self.expected_for_eval = gesture_name_or_none
        self.accuracy_win.clear()

    def get_eval_stats(self):
        """
        Returns: (n, correct, acc or None) over last 20 frames.
        acc 在 n >= 20 時才會有值。
        """
        n = len(self.accuracy_win)
        c = sum(self.accuracy_win)
        acc = (c / n * 100.0) if n >= self.accuracy_win.maxlen and n > 0 else None
        current = self.vote[-1]  
        return  n, current, c, acc   

    def get_acc(self):
        """
        根據最近 self.vote 計算「目前手勢的穩定度」：
        - current: 最新一幀的投票結果（self.vote[-1]）
        - n: 視窗內總幀數
        - correct: 其中有幾幀跟 current 一樣
        - acc: 百分比（n > 0 時才有值） correct / n
        """
        if not self.vote:
            return 0, "None", 0, None

        current = self.vote[-1]       
        #n = len(self.vote)
        n = len(self.accuracy_win)
        #correct = sum(1 for g in self.vote if g == current)
        correct =sum(1 for g in self.accuracy_win if g == current)
        acc = (correct / n * 100.0) if n > 0 else None
        return n, current, correct, acc   

    def get_acc(self):
        """
        根據最近 self.vote 計算「目前手勢的穩定度」：
        - current: 最新一幀的投票結果（self.vote[-1]）
        - n: 視窗內總幀數
        - correct: 其中有幾幀跟 current 一樣
        - acc: 百分比（n > 0 時才有值） correct / n
        """
        if not self.vote:
            return 0, "None", 0, None

        current = self.vote[-1]         
        n = len(self.vote)
        correct = sum(1 for g in self.vote if g == current)
        acc = (correct / n * 100.0) if n > 0 else None
        return n, current, correct, acc   

    def close(self):
        self.hands.close()


# =========================
# 4) Camera Thread
# =========================
def camera_thread(shared: SharedState):
    """
    開一條執行緒：
    - 不斷讀取相機
    - 丟進 MediaPipe 做手勢辨識
    - 把投票後的手勢寫進 shared.set_gesture(...)
    - 把 debug 畫面 & FPS & raw gesture & landmarks 寫進 shared.set_camera_view(...)
    """
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

            voted, raw, draw_lms, lmk_data = recog.recognize(rgb)
            shared.set_gesture(voted)

            dbg = frame.copy()
            dbg = recog.draw_landmarks(dbg, draw_lms)

            cnt += 1
            now = time.time()
            if now - t0 >= 1.0:
                fps_disp = cnt / (now - t0)
                cnt, t0 = 0, now
            shared.set_camera_view(dbg, fps_disp, raw, lmk_data)
            # cv2.putText(
            #     dbg,
            #     f"CamFPS:{fps_disp:.1f}",
            #     (8, 16),
            #     cv2.FONT_HERSHEY_SIMPLEX,
            #     0.5,
            #     (0, 255, 0),
            #     1,
            #     cv2.LINE_AA,
            # )
            # txt_l = f"L:{raw.get('Left', 'None')}"
            # txt_r = f"R:{raw.get('Right', 'None')}"
            # cv2.putText(
            #     dbg,
            #     txt_l,
            #     (8, 34),
            #     cv2.FONT_HERSHEY_SIMPLEX,
            #     0.55,
            #     (255, 255, 0),
            #     1,
            #     cv2.LINE_AA,
            # )
            # cv2.putText(
            #     dbg,
            #     txt_r,
            #     (72, 34),
            #     cv2.FONT_HERSHEY_SIMPLEX,
            #     0.55,
            #     (255, 0, 255),
            #     1,
            #     cv2.LINE_AA,
            # )

            # shared.set_camera_view(dbg, fps_disp, raw, lmk_data)

            # small = cv2.resize(dbg, (320, 180))
            # cv2.imshow("GestiX Camera (Debug)", small)
            # if cv2.waitKey(1) & 0xFF == 27:
            #     shared.set_running(False)
            #     break

    except Exception as e:
        print(f"[Camera] Unexpected error: {e}")
    finally:
        cap.release()
        recog.close()
        #cv2.destroyAllWindows()


# =========================
# 5) Standalone debug run
# =========================
if __name__ == "__main__":
    shared = SharedState()
    th = threading.Thread(target=camera_thread, args=(shared,), daemon=True)
    th.start()
    print("Running MediaPipe module... (Press ESC in camera window to exit)")

    try:
        while shared.is_running():
            time.sleep(0.05)
    except KeyboardInterrupt:
        shared.set_running(False)

    th.join()
    print("MediaPipe module closed.")
