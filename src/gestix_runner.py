# gestix_runner.py (Python 3.10) - Refactored Version
import threading
import time
import math
import collections
import numpy as np
import cv2
import mediapipe as mp
import pygame

# ===== 1. Constants & Configuration (集中管理，方便調整) =====
class Config:
    CAM_INDEX = 0
    FRAME_W, FRAME_H = 640, 480
    VOTE_FRAMES = 5
    TRIGGER_COOLDOWN = 0.30   # seconds
    WAVE_WINDOW = 8
    JUMP_VELOCITY = -15
    GRAVITY = 1
    SLIDE_TIME = 0.6
    OBST_SPEED = 6
    # PyGame Colors
    COLOR_WHITE = (245, 245, 245)
    COLOR_GROUND = (220, 220, 220)
    COLOR_PLAYER = (50, 120, 255)
    COLOR_PLAYER_JUMP = (255, 120, 50)
    COLOR_OBSTACLE = (40, 40, 40)
    COLOR_TEXT = (30, 30, 30)
    COLOR_PAUSED = (180, 0, 0)

# ===== 2. Shared State (使用 dataclass 讓結構更清晰) =====
class SharedState:
    def __init__(self):
        self.gesture = "None"
        self.gesture_ts = 0.0
        self.running = True
        self.lock = threading.Lock()
        self.frame_info=None

    def set_gesture(self, gesture):
        with self.lock:
            now = time.time()
            if gesture != "None" and (now - self.gesture_ts >= Config.TRIGGER_COOLDOWN):
                self.gesture = gesture
                self.gesture_ts = now

    def get_gesture(self):
        with self.lock:
            g = self.gesture
            self.gesture = "None" # Consume gesture
            return g

    def is_running(self):
        with self.lock:
            return self.running

    def set_running(self, value):
        with self.lock:
            self.running = value

    def set_camera_view(self,frame,fps_display,raw_gesture,voted_gesture):
        with self.lock:
            if frame is None:
                self.frame_info=frame
                return
            self.frame_info={
                "frame":frame.copy(),
                "fps_display":fps_display,
                "raw_gesture":raw_gesture,
                "voted_gesture":voted_gesture
            }
    
    def get_camera_view(self):
        with self.lock:
            if not self.frame_info:
                return None
            info=self.frame_info.copy()
            info["frame"]=info["frame"].copy()
            return info

# ===== 3. Gesture Recognition Logic (升級演算法 + 描點) =====
class HandGestureRecognizer:
    def __init__(self):
        self.mp_hands = mp.solutions.hands
        self.mp_draw = mp.solutions.drawing_utils # <--- 新增：用於描點
        self.hands = self.mp_hands.Hands(
            max_num_hands=1,
            model_complexity=0,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6
        )
        self.gesture_queue = collections.deque(maxlen=Config.VOTE_FRAMES)
        self.wrist_hist = collections.deque(maxlen=Config.WAVE_WINDOW)
        
        # --- 描點樣式 (來自您的參考程式碼) ---
        self.hand_lms_style = self.mp_draw.DrawingSpec(color=(0, 0, 255), thickness=3)
        self.hand_con_style = self.mp_draw.DrawingSpec(color=(0, 255, 0), thickness=5)
        # ------------------------------------
        
        self.tip_ids = [4, 8, 12, 16, 20] # 5根手指的指尖 ID

    def _dist(self, p1, p2):
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

    def _get_finger_status(self, landmarks):
        """
        回傳一個陣列 [Thumb, Index, Middle, Ring, Pinky]，1=Up, 0=Down
        """
        fingers_up = [0] * 5
        
        # 處理大拇指 (唯一水平判斷的手指)
        # 注意：影像已水平翻轉，所以 "左" <-> "右"
        if landmarks[self.tip_ids[0]].x < landmarks[self.tip_ids[0] - 1].x:
            fingers_up[0] = 1
            
        # 處理其他四根手指 (垂直判斷)
        for i in range(1, 5):
            if landmarks[self.tip_ids[i]].y < landmarks[self.tip_ids[i] - 2].y:
                fingers_up[i] = 1
        return fingers_up

    def _is_wave(self, landmarks):
        # 揮手演算法保持不變，它已經足夠穩定了
        self.wrist_hist.append((landmarks[0].x,landmarks[0].y)) # 追蹤手腕座標
        if len(self.wrist_hist) < Config.WAVE_WINDOW: return False
        xs = [p[0] - np.mean([p[0] for p in self.wrist_hist]) for p in self.wrist_hist]
        sign_changes = np.sum(np.diff(np.sign(xs)) != 0)
        amplitude = max(xs) - min(xs)
        return sign_changes >= 2 and amplitude > 0.15 # 偵測到左右擺動

    def recognize(self, frame_rgb):
        """
        辨識手勢，並回傳 (voted_gesture, raw_gesture, landmarks)
        """
        res = self.hands.process(frame_rgb)
        cur_raw = "None"
        landmarks_list = None
        
        if res.multi_hand_landmarks:
            # 取得 21 個點的 (x, y) 座標
            lm = res.multi_hand_landmarks[0]
            landmarks_list = lm.landmark
            
            # --- 強化版演算法：手指計數 ---
            fingers = self._get_finger_status(landmarks_list)
            
            if self._is_wave(landmarks_list):
                cur_raw = "Wave"
            elif fingers == [1, 0, 0, 0, 0]: # 只有大拇指
                cur_raw = "ThumbUp"
            elif fingers == [0, 0, 0, 0, 0]: # 0 根手指
                cur_raw = "Fist"
            elif fingers == [1, 1, 1, 1, 1]: # 5 根手指
                cur_raw = "Open"
            # ---------------------------------
            
        # 投票機制 (去抖動) 
        self.gesture_queue.append(cur_raw)
        voted = max(set(self.gesture_queue), key=self.gesture_queue.count)
        
        # 回傳 1.投票後的穩定手勢 2.原始辨識手勢 3.關鍵點(給描點用)
        return voted, cur_raw, res.multi_hand_landmarks

    def draw_landmarks(self, frame, multi_hand_landmarks):
        """
        在影像上繪製關鍵點和骨架 (使用您參考程式碼的樣式)
        """
        if multi_hand_landmarks:
            for hand_lms in multi_hand_landmarks:
                self.mp_draw.draw_landmarks(
                    frame, 
                    hand_lms, 
                    self.mp_hands.HAND_CONNECTIONS,
                    self.hand_lms_style, 
                    self.hand_con_style
                )
        return frame

    def close(self):
        self.hands.close()

# ===== 4. Camera Thread (加入 try...finally 強制釋放資源) =====
def camera_thread(shared_state: SharedState):
    recognizer = HandGestureRecognizer()
    cap = cv2.VideoCapture(Config.CAM_INDEX)

    if not cap.isOpened():
        print(f"錯誤：無法開啟索引為 {Config.CAM_INDEX} 的攝影機。")
        print("請檢查：1. 攝影機是否被其他程式佔用？ 2. CAM_INDEX 是否正確？ 3. 系統是否已授權？")
        shared_state.set_running(False)
        return
    else:
        print(f"攝影機 {Config.CAM_INDEX} 已成功開啟！")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, Config.FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.FRAME_H)
    fps_t0, fps_cnt, fps_display = time.time(), 0, 0.0

    try:
        # ===== 這是主迴圈 =====
        while shared_state.is_running():
            ok, frame = cap.read()
            if not ok or frame is None:
                print("警告：讀取攝影機影像失敗，可能中斷。")
                time.sleep(0.5) # 稍作等待
                continue # 跳過這一幀

            frame = cv2.flip(frame, 1) # 翻轉成鏡像，符合直覺
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # 1. 辨識手勢
            voted_gesture, raw_gesture, landmarks = recognizer.recognize(rgb)
            
            # 2. 將辨識結果傳給遊戲
            shared_state.set_gesture(voted_gesture)

            # 3. 繪製骨架 (使用新方法)
            frame = recognizer.draw_landmarks(frame, landmarks)

            # --- Debug Display (指標) ---
            fps_cnt += 1
            if time.time() - fps_t0 >= 1.0:
                fps_display = fps_cnt / (time.time() - fps_t0)
                fps_cnt, fps_t0 = 0, time.time()

            shared_state.set_camera_view(frame,fps_display,raw_gesture,voted_gesture)
            
            # 顯示更豐富的指標
            # cv2.putText(frame, f"FPS: {fps_display:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            # cv2.putText(frame, f"Raw: {raw_gesture}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
            # cv2.putText(frame, f"Voted: {voted_gesture}", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            # cv2.imshow("GestiX Camera", frame)

            # ---------------------------

            # if cv2.waitKey(1) & 0xFF == 27: # ESC
            #     shared_state.set_running(False)
    
    except Exception as e:
        print(f"攝影機執行緒發生未預期錯誤: {e}")
        shared_state.set_running(False) # 通知主程式一起關閉

    finally:
        # ===== 這裡最關鍵 =====
        # 無論迴圈如何結束 (正常結束或出錯)，都強制執行
        print("正在釋放攝影機資源...")
        cap.release()
        cv2.destroyAllWindows()
        recognizer.close()
        print("攝影機資源已釋放。")

# ===== 5. Game Logic (也封裝成類別) =====
class RunnerGame:
    def __init__(self, shared_state: SharedState):
        pygame.init()
        self.W, self.H = 800, 400
        self.screen = pygame.display.set_mode((self.W, self.H))
        pygame.display.set_caption("GestiX Runner")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(None, 24)
        self.shared_state = shared_state
        self.reset()

    def reset(self):
        self.player = pygame.Rect(100, self.H - 120, 40, 60)
        self.vy = 0
        self.on_ground = True
        self.sliding_until = 0
        self.obstacles = []
        self.spawn_timer = 0
        self.score = 0
        self.paused = True

    def spawn_obstacle(self):
        h = np.random.randint(30, 60)
        w = np.random.randint(20, 35)
        rect = pygame.Rect(self.W, self.H - 60 - h, w, h)
        self.obstacles.append(rect)

    def handle_gesture(self, g):
        if g == "ThumbUp":
            if self.paused: # 如果遊戲結束，重新開始
                if not self.shared_state.is_running(): self.reset() # 簡易的重新開始邏輯
            self.paused = not self.paused # 切換暫停狀態
        
        if self.paused: return

        if g == "Open" and self.on_ground:
            self.vy = Config.JUMP_VELOCITY
            self.on_ground = False
        elif g == "Fist":
            self.sliding_until = time.time() + Config.SLIDE_TIME
        elif g == "Wave":
            self.paused = True

    def update(self, dt):
        if self.paused: return

        self.vy += Config.GRAVITY
        self.player.y += self.vy
        ground_y = self.H - 120
        if self.player.y >= ground_y:
            self.player.y = ground_y
            self.vy = 0
            self.on_ground = True

        self.player.height = 35 if time.time() < self.sliding_until else 60

        self.spawn_timer += dt
        if self.spawn_timer > np.random.uniform(900, 1500): # 隨機生成障礙物，增加趣味性
            self.spawn_timer = 0
            self.spawn_obstacle()

        for obs in list(self.obstacles):
            obs.x -= Config.OBST_SPEED
            if obs.right < 0:
                self.obstacles.remove(obs)
                self.score += 1
            if obs.colliderect(self.player):
                self.paused = True # 遊戲結束

    def draw(self):
        self.screen.fill(Config.COLOR_WHITE)
        pygame.draw.rect(self.screen, Config.COLOR_GROUND, (0, self.H - 60, self.W, 60))

        color = Config.COLOR_PLAYER if self.on_ground else Config.COLOR_PLAYER_JUMP
        pygame.draw.rect(self.screen, color, self.player, border_radius=6)

        for obs in self.obstacles:
            pygame.draw.rect(self.screen, Config.COLOR_OBSTACLE, obs, border_radius=4)

        score_text = self.font.render(f"Score: {self.score}", True, Config.COLOR_TEXT)
        fps_text = self.font.render(f"FPS: {self.clock.get_fps():.1f}", True, Config.COLOR_TEXT)
        self.screen.blit(score_text, (10, 10))
        self.screen.blit(fps_text, (10, 30))
        
        hint = "ThumbUp: Start/Pause | Open: Jump | Fist: Slide | Wave: Pause | ESC: Quit"
        self.screen.blit(self.font.render(hint, True, Config.COLOR_TEXT), (10, 60))

        if self.paused:
            pause_text = "GAME OVER. ThumbUp to RESTART" if self.score > 0 else "PAUSED. ThumbUp to START"
            text_surf = self.font.render(pause_text, True, Config.COLOR_PAUSED)
            text_rect = text_surf.get_rect(center=(self.W // 2, self.H // 2))
            self.screen.blit(text_surf, text_rect)

        pygame.display.flip()

    def run(self):
        while self.shared_state.is_running():
            dt = self.clock.tick(60)

            for e in pygame.event.get():
                if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                    self.shared_state.set_running(False)
            
            gesture = self.shared_state.get_gesture()
            if gesture != "None":
                self.handle_gesture(gesture)

            self.update(dt)
            self.draw()

            view=self.shared_state.frame_info()
        if view is not None:
            frame=view["frame"]
            fps_display=view["fps_display"]
            raw_gesture=view["raw_gesture"]
            voted_gesture=view["voted_gesture"]
            cv2.putText(frame, f"FPS: {fps_display:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            cv2.putText(frame, f"Raw: {raw_gesture}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
            cv2.putText(frame, f"Voted: {voted_gesture}", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.imshow("GestiX Camera", frame)

            if cv2.waitKey(1) & 0xFF == 27: # ESC
                self.shared_state.set_running(False)


        pygame.quit()

# ===== 6. Main Execution =====
def main():
    shared_state = SharedState()
    
    cam_thread = threading.Thread(target=camera_thread, args=(shared_state,), daemon=True)
    cam_thread.start()
    
    game = RunnerGame(shared_state)
    game.run()
    
    cam_thread.join()
    print("Program finished.")

if __name__ == "__main__":
    main()