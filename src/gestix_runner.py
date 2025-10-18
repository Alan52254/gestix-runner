# gestix_runner.py  (Python 3.10)
import threading, time, math, collections
import numpy as np
import cv2
import mediapipe as mp
import pygame

# ===== Config =====
CAM_INDEX = 0
FRAME_W, FRAME_H = 640, 480
VOTE_FRAMES = 5
TRIGGER_COOLDOWN = 0.30   # seconds
WAVE_WINDOW = 8
JUMP_VELOCITY = -15
GRAVITY = 1
SLIDE_TIME = 0.6
OBST_SPEED = 6

# ===== Shared state with lock =====
shared_lock = threading.Lock()
shared = {"gesture": "None", "gesture_ts": 0.0, "running": True}

gesture_queue = collections.deque(maxlen=VOTE_FRAMES)
wrist_hist = collections.deque(maxlen=WAVE_WINDOW)

def dist(p1, p2):
    return math.hypot(p1[0]-p2[0], p1[1]-p2[1])

def is_thumb_up(pts, base):
    wrist = pts[0]; thumb_tip = pts[4]; index_tip = pts[8]
    d_ti = dist(thumb_tip, index_tip) / base
    d_tw = dist(thumb_tip, wrist) / base
    d_iw = dist(index_tip, wrist) / base
    return (d_ti > 0.8) and (d_tw > 1.0) and (d_ti > 0.7*d_iw)

def is_open_hand(pts, base):
    palm = pts[0]
    tips = [pts[4], pts[8], pts[12], pts[16], pts[20]]
    ds = [dist(t, palm)/base for t in tips]
    return sum(d > 0.9 for d in ds) >= 4

def is_fist(pts, base):
    palm = pts[9]  # approx palm center
    tips = [pts[8], pts[12], pts[16], pts[20]]
    return all((dist(t, palm)/base) < 0.6 for t in tips)

def is_wave():
    if len(wrist_hist) < WAVE_WINDOW: return False
    xs = [x - np.mean([p[0] for p in wrist_hist]) for x,_ in wrist_hist]
    sign_changes = np.sum(np.diff(np.sign(xs)) != 0)
    amplitude = max(xs) - min(xs)
    return sign_changes >= 2 and amplitude > 0.15

def camera_thread():
    mp_hands = mp.solutions.hands
    cap = cv2.VideoCapture(CAM_INDEX)

    # ============= 請在這裡加入下面的檢查碼 =============
    if not cap.isOpened():
        print(f"錯誤：無法開啟索引為 {CAM_INDEX} 的攝影機。")
        print("請檢查：1. 攝影機是否被其他程式佔用？ 2. CAM_INDEX 是否正確？ 3. 系統是否已授權？")
        with shared_lock:
            shared["running"] = False # 通知主程式結束
        return # 直接結束這個執行緒
    else:
        print(f"攝影機 {CAM_INDEX} 已成功開啟！")
    # =======================================================

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)
    mp_hands = mp.solutions.hands
    cap = cv2.VideoCapture(CAM_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)
    fps_t0, fps_cnt = time.time(), 0
    fps_display = 0.0

    with mp_hands.Hands(max_num_hands=1, model_complexity=0,
                        min_detection_confidence=0.6,
                        min_tracking_confidence=0.6) as hands:
        while True:
            with shared_lock:
                if not shared["running"]:
                    break

            ok, frame = cap.read()
            if not ok: break
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = hands.process(rgb)

            cur = "None"
            if res.multi_hand_landmarks:
                lm = res.multi_hand_landmarks[0].landmark
                pts = [(lm[i].x, lm[i].y) for i in range(21)]
                wrist_hist.append(pts[0])

                # base distance: wrist to middle_mcp
                base = dist(pts[0], pts[9]) + 1e-6

                if is_wave():
                    cur = "Wave"
                elif is_thumb_up(pts, base):
                    cur = "ThumbUp"
                elif is_open_hand(pts, base):
                    cur = "Open"
                elif is_fist(pts, base):
                    cur = "Fist"
                else:
                    cur = "None"

                # draw landmarks (debug)
                for x,y in pts:
                    cv2.circle(frame, (int(x*FRAME_W), int(y*FRAME_H)), 2, (0,255,0), -1)

            gesture_queue.append(cur)
            voted = max(set(gesture_queue), key=gesture_queue.count)

            now = time.time()
            with shared_lock:
                if voted != "None" and (now - shared["gesture_ts"] >= TRIGGER_COOLDOWN):
                    shared["gesture"] = voted
                    shared["gesture_ts"] = now

            # FPS meter
            fps_cnt += 1
            if time.time() - fps_t0 >= 1.0:
                fps_display = fps_cnt / (time.time() - fps_t0)
                fps_cnt, fps_t0 = 0, time.time()

            cv2.putText(frame, f"Gesture(voted): {voted}", (10,30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
            cv2.putText(frame, f"FPS:{fps_display:.1f}", (10,60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,255), 2)
            cv2.imshow("GestiX Camera", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                with shared_lock: shared["running"] = False
                break

    cap.release()
    cv2.destroyAllWindows()

class RunnerGame:
    def __init__(self):
        pygame.init()
        self.W, self.H = 800, 400
        self.screen = pygame.display.set_mode((self.W, self.H))
        pygame.display.set_caption("GestiX Runner (MVP)")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(None, 24)

        self.player = pygame.Rect(100, self.H-120, 40, 60)
        self.vy = 0; self.on_ground = True
        self.sliding_until = 0
        self.obstacles = []; self.spawn_timer = 0
        self.score = 0; self.paused = True
        self.running = True

    def spawn_obstacle(self):
        h = np.random.randint(30,60); w = np.random.randint(20,35)
        rect = pygame.Rect(self.W, self.H-60-h, w, h)
        self.obstacles.append(rect)

    def handle_gesture(self, g):
        if g == "ThumbUp": self.paused = False
        if self.paused: return
        if g == "Open" and self.on_ground:
            self.vy = JUMP_VELOCITY; self.on_ground = False
        elif g == "Fist":
            self.sliding_until = time.time() + SLIDE_TIME
        elif g == "Wave":
            self.paused = True

    def update(self, dt):
        if self.paused: return
        self.vy += GRAVITY; self.player.y += self.vy
        ground_y = self.H - 120
        if self.player.y >= ground_y:
            self.player.y = ground_y; self.vy = 0; self.on_ground = True

        self.player.height = 35 if time.time() < self.sliding_until else 60

        self.spawn_timer += dt
        if self.spawn_timer > 1100:
            self.spawn_timer = 0; self.spawn_obstacle()

        for obs in list(self.obstacles):
            obs.x -= OBST_SPEED
            if obs.right < 0:
                self.obstacles.remove(obs); self.score += 1
            if obs.colliderect(self.player):
                self.paused = True

    def draw(self, fps):
        self.screen.fill((245,245,245))
        pygame.draw.rect(self.screen, (220,220,220), (0, self.H-60, self.W, 60))
        color = (50,120,255) if self.on_ground else (255,120,50)
        pygame.draw.rect(self.screen, color, self.player, border_radius=6)
        for obs in self.obstacles:
            pygame.draw.rect(self.screen, (40,40,40), obs, border_radius=4)
        t1 = self.font.render(f"Score: {self.score}", True, (0,0,0))
        with shared_lock:
            g = shared["gesture"]
        t2 = self.font.render(f"Gesture: {g}", True, (0,0,0))
        t3 = self.font.render(f"FPS(Game): {fps:.1f}", True, (0,0,0))
        self.screen.blit(t1,(10,10)); self.screen.blit(t2,(10,30)); self.screen.blit(t3,(10,50))
        hint = "ThumbUp=Start/Resume | Open=Jump | Fist=Slide | Wave=Pause | ESC=Quit"
        self.screen.blit(self.font.render(hint, True, (30,30,30)), (10, 80))
        if self.paused:
            self.screen.blit(self.font.render("PAUSED (ThumbUp to Start/Resume)", True, (180,0,0)), (220, 150))
        pygame.display.flip()

    def run(self):
        while True:
            with shared_lock:
                if not shared["running"]: break
            dt = self.clock.tick(60)
            fps = self.clock.get_fps()
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    with shared_lock: shared["running"] = False
                if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                    with shared_lock: shared["running"] = False
            # consume gesture
            with shared_lock:
                g = shared["gesture"]; shared["gesture"] = "None"
            if g != "None": self.handle_gesture(g)
            self.update(dt); self.draw(fps)
        pygame.quit()

def main():
    t = threading.Thread(target=camera_thread, daemon=True)
    t.start()
    RunnerGame().run()
    t.join()

if __name__ == "__main__":
    main()
