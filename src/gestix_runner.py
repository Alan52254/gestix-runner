# gestix_runner_w1_final.py (Python 3.10+)
# GestiX Runner — integrated single-file MVP with OK/Victory, validation, and robust state logic

import threading
import time
import math
import collections
from collections import deque
import numpy as np
import cv2
import mediapipe as mp
import pygame

# =========================
# 1) Configuration
# =========================
class Config:
    # Camera
    CAM_INDEX = 0
    CAM_W, CAM_H = 640, 360   # good balance for CPU FPS

    # Game
    SCREEN_W, SCREEN_H = 800, 400
    GAME_FPS = 60
    SCROLL_SPEED = 5

    # Physics
    GRAVITY = 0.8
    JUMP_VELOCITY = -15
    SLIDE_TIME = 0.5  # s
    BULLET_SPEED = 10
    ENEMY_SPEED = 2

    # Gestures / Debounce
    MAX_HANDS = 2
    VOTE_FRAMES = 2 #要及時跳調小反應加快
    TRIGGER_COOLDOWN = 0.15  # s    ＃縮短再次觸發的等待時間
    WAVE_WINDOW = 10         # frames for wrist x oscillation
    WAVE_MIN_SWINGS = 2
    WAVE_MIN_AMPLITUDE = 0.15

    # Gesture mapping (clear separation of responsibilities)
    GESTURE_MAPPING = {
        "Fist": "START_GAME",      # only in START
        "Open": "JUMP",
        "Gun": "SHOOT",
        "OK": "SPEED_UP",          # new
        "Victory": "ULTI",         # new
        "ThumbUp": "RESTART",      # only in GAME_OVER
        "Wave": "PAUSE_TOGGLE",
        "DualOpen": "ULTI"         # optional: both hands open also triggers ULTI
    }
    # One-shot (consumed) gestures
    CONSUME_GESTURES = {"Open", "Gun", "OK", "Victory", "ThumbUp", "DualOpen"}

    # Colors (placeholder block art)
    COLOR_SKY = (135, 206, 235)
    COLOR_GROUND = (124, 252, 0)
    COLOR_BRICK = (184, 134, 11)
    COLOR_PLAYER = (255, 0, 0)
    COLOR_ENEMY = (139, 69, 19)
    COLOR_COIN = (255, 215, 0)
    COLOR_BULLET = (255, 140, 0)
    COLOR_TEXT = (30, 30, 30)
    COLOR_UI_PAUSED = (0, 0, 0, 160)


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
        self._recognizer_ref = None  # for validation HUD

    # running
    def set_running(self, val: bool):
        with self._lock:
            self._running = val

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    # gesture (debounced, consumed)
    def set_gesture(self, gesture: str):
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

    # camera view bundle
    def set_camera_view(self, frame, fps, raw_gestures, landmarks_data):
        with self._lock:
            self._camera_view = {
                "frame": frame.copy(),
                "fps": fps,
                "raw_gestures": raw_gestures,
                "landmarks": landmarks_data
            }

    def get_camera_view(self):
        with self._lock:
            return self._camera_view.copy() if self._camera_view else None

    # recognizer ref (for HUD of validation)
    def set_recognizer_ref(self, recognizer):
        with self._lock:
            self._recognizer_ref = recognizer

    def get_recognizer_ref(self):
        with self._lock:
            return self._recognizer_ref


# =========================
# 3) Gesture Recognition
# =========================
class HandGestureRecognizer:
    def __init__(self):
        self.mp_hands = mp.solutions.hands
        self.mp_draw = mp.solutions.drawing_utils
        self.hands = self.mp_hands.Hands(
            max_num_hands=Config.MAX_HANDS,
            model_complexity=0,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6
        )
        self.hand_lms_style = self.mp_draw.DrawingSpec(color=(0, 0, 255), thickness=2)
        self.hand_con_style = self.mp_draw.DrawingSpec(color=(0, 255, 0), thickness=2)

        self.tip_ids = [4, 8, 12, 16, 20]
        self.gesture_queue = deque(maxlen=Config.VOTE_FRAMES)

        # wave detection history (wrist x normalized)
        self.wrist_hist = deque(maxlen=Config.WAVE_WINDOW)

        # validation window for accuracy (20 frames)
        self.accuracy_win = deque(maxlen=20)
        self.expected_for_eval = None

    # ---------- helpers ----------
    @staticmethod
    def _dist2d(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def _get_finger_status(self, lms, handedness: str):
        """Return [thumb,index,middle,ring,pinky] up/down (1/0)."""
        fingers = [0]*5
        # thumb (horizontal)
        if (handedness == "Right" and lms[self.tip_ids[0]].x < lms[self.tip_ids[0]-1].x) or \
           (handedness == "Left"  and lms[self.tip_ids[0]].x > lms[self.tip_ids[0]-1].x):
            fingers[0] = 1
        # other fingers (vertical)
        for i in range(1,5):
            fingers[i] = 1 if lms[self.tip_ids[i]].y < lms[self.tip_ids[i]-2].y else 0
        return fingers

    def _is_gun(self, fingers):
        # index up only (allow thumb up sometimes)
        return (fingers[1] == 1) and (sum([fingers[2],fingers[3],fingers[4]]) == 0)

    def _is_ok(self, lms, handedness: str):
        # Thumb tip (4) close to index tip (8), others mostly folded
        base = self._dist2d((lms[0].x,lms[0].y), (lms[9].x,lms[9].y)) + 1e-6
        d48 = self._dist2d((lms[4].x,lms[4].y), (lms[8].x,lms[8].y)) / base
        fingers = self._get_finger_status(lms, handedness)
        return d48 < 0.35 and fingers[1] == 1 and sum(fingers[2:]) <= 1

    def _is_victory(self, fingers):
        # index + middle up, others down (allow thumb flexible)
        return (fingers[1] == 1 and fingers[2] == 1 and fingers[3] == 0 and fingers[4] == 0)

    def _single_hand_gesture(self, lms, handedness: str):
        fingers = self._get_finger_status(lms, handedness)
        if self._is_ok(lms, handedness):     return "OK"
        if self._is_victory(fingers):        return "Victory"
        if self._is_gun(fingers):            return "Gun"
        if fingers == [1,0,0,0,0]:           return "ThumbUp"
        if fingers == [0,0,0,0,0]:           return "Fist"
        if fingers == [1,1,1,1,1]:           return "Open"
        return "None"

    def _update_wave(self, wrist_x_norm: float):
        self.wrist_hist.append(wrist_x_norm)
        if len(self.wrist_hist) < self.wrist_hist.maxlen:
            return False
        xs = np.array(self.wrist_hist)
        xs = xs - xs.mean()
        sign_changes = np.sum(np.diff(np.sign(xs)) != 0)
        amplitude = xs.max() - xs.min()
        return (sign_changes >= Config.WAVE_MIN_SWINGS) and (amplitude > Config.WAVE_MIN_AMPLITUDE)

    # ---------- public ----------
    def recognize(self, frame_rgb):
        res = self.hands.process(frame_rgb)
        raw_g = {"Left": "None", "Right": "None"}
        final_gesture = "None"
        draw_lms = res.multi_hand_landmarks
        landmarks_data = None
        wave_flag = False

        if res.multi_hand_landmarks:
            landmarks_data = []
            for i, hand_lms in enumerate(res.multi_hand_landmarks):
                handed = res.multi_handedness[i].classification[0].label  # "Left"/"Right"
                # for wave detection (use wrist x)
                wrist = hand_lms.landmark[0]
                wave_flag = wave_flag or self._update_wave(wrist.x)

                # per hand gesture
                g = self._single_hand_gesture(hand_lms.landmark, handed)
                raw_g[handed] = g

                # store 21 (x,y,z)
                pts = [(lm.x, lm.y, lm.z) for lm in hand_lms.landmark]
                landmarks_data.append({"handedness": handed, "landmarks": pts})

            # combine hands
            if raw_g["Left"] == "Open" and raw_g["Right"] == "Open":
                final_gesture = "DualOpen"
            elif wave_flag:
                final_gesture = "Wave"
            elif raw_g["Right"] != "None":
                final_gesture = raw_g["Right"]
            elif raw_g["Left"] != "None":
                final_gesture = raw_g["Left"]

        # vote & push to validation window
        self.gesture_queue.append(final_gesture)
        voted = max(set(self.gesture_queue), key=self.gesture_queue.count) if self.gesture_queue else "None"

        if self.expected_for_eval is not None:
            self.accuracy_win.append(1 if voted == self.expected_for_eval else 0)

        return voted, raw_g, draw_lms, landmarks_data

    def draw_landmarks(self, frame, multi_hand_landmarks):
        if multi_hand_landmarks:
            for hand_lms in multi_hand_landmarks:
                self.mp_draw.draw_landmarks(
                    frame, hand_lms, self.mp_hands.HAND_CONNECTIONS,
                    self.hand_lms_style, self.hand_con_style
                )
        return frame

    # Validation API
    def set_expected_for_eval(self, gesture_name_or_none):
        self.expected_for_eval = gesture_name_or_none
        self.accuracy_win.clear()

    def get_eval_stats(self):
        """Returns (n, correct, acc or None) over the 20-frame window."""
        n = len(self.accuracy_win)
        c = sum(self.accuracy_win)
        acc = (c/n*100.0) if n >= 20 else None
        return n, c, acc

    def close(self):
        self.hands.close()


# =========================
# 4) Camera Thread
# =========================
def camera_thread(shared: SharedState):
    recognizer = HandGestureRecognizer()
    shared.set_recognizer_ref(recognizer)

    cap = cv2.VideoCapture(Config.CAM_INDEX)
    if not cap.isOpened():
        print(f"[Camera] Cannot open camera index {Config.CAM_INDEX}")
        shared.set_running(False)
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, Config.CAM_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.CAM_H)

    fps_t0, fps_cnt, fps_display = time.time(), 0, 0.0

    try:
        while shared.is_running():
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.02)
                continue

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            voted_g, raw_g, draw_lms, lmk_data = recognizer.recognize(rgb)
            shared.set_gesture(voted_g)

            # (Optional) draw landmarks – disable for higher FPS if needed
            frame_dbg = frame.copy()
            frame_dbg = recognizer.draw_landmarks(frame_dbg, draw_lms)

            # FPS
            fps_cnt += 1
            now = time.time()
            if now - fps_t0 >= 1.0:
                fps_display = fps_cnt / (now - fps_t0)
                fps_cnt, fps_t0 = 0, now

            shared.set_camera_view(frame_dbg, fps_display, raw_g, lmk_data)

    except Exception as e:
        print(f"[Camera] Unexpected error: {e}")
    finally:
        cap.release()
        recognizer.close()


# =========================
# 5) Game Sprites
# =========================
class Player(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.image = pygame.Surface((32, 32))
        self.image.fill(Config.COLOR_PLAYER)
        self.rect = self.image.get_rect(bottomleft=(x, y))

        self.vel_y = 0
        self.on_ground = False
        self.is_sliding = False
        self.slide_until = 0

        self.shoot_cooldown = 0  # in frames

    def update(self, platforms):
        # gravity
        if not self.on_ground:
            self.vel_y += Config.GRAVITY
            self.rect.y += self.vel_y

        # ground/platform collision
        self.on_ground = False
        collided = pygame.sprite.spritecollide(self, platforms, False)
        for plat in collided:
            if self.vel_y > 0:
                self.rect.bottom = plat.rect.top
                self.vel_y = 0
                self.on_ground = True

        # slide
        if self.is_sliding and time.time() > self.slide_until:
            self.is_sliding = False
            # restore size
            old_center = self.rect.center
            self.image = pygame.Surface((32, 32))
            self.image.fill(Config.COLOR_PLAYER)
            self.rect = self.image.get_rect(center=old_center)

        if self.shoot_cooldown > 0:
            self.shoot_cooldown -= 1

    def jump(self):
        if self.on_ground:
            self.vel_y = Config.JUMP_VELOCITY
            self.on_ground = False

    def slide(self):
        if self.on_ground and not self.is_sliding:
            self.is_sliding = True
            self.slide_until = time.time() + Config.SLIDE_TIME
            # shrink bounding box (become shorter)
            old_bottomleft = self.rect.bottomleft
            self.image = pygame.Surface((32, 16))
            self.image.fill(Config.COLOR_PLAYER)
            self.rect = self.image.get_rect(bottomleft=old_bottomleft)

    def shoot(self, bullets, all_sprites):
        if self.shoot_cooldown <= 0:
            b = Bullet(self.rect.right, self.rect.centery)
            bullets.add(b)
            all_sprites.add(b)
            self.shoot_cooldown = int(0.5 * Config.GAME_FPS)  # 0.5s


class Platform(pygame.sprite.Sprite):
    def __init__(self, x, y, w, h, is_brick=False):
        super().__init__()
        self.image = pygame.Surface((w, h))
        self.image.fill(Config.COLOR_BRICK if is_brick else Config.COLOR_GROUND)
        self.rect = self.image.get_rect(topleft=(x, y))
        self.is_brick = is_brick


class Enemy(pygame.sprite.Sprite):
    def __init__(self, x, y,w=32,h=32):
        super().__init__()
        self.image = pygame.Surface((w, h))
        self.image.fill(Config.COLOR_ENEMY)
        self.rect = self.image.get_rect(bottomleft=(x, y))
        self.speed = Config.ENEMY_SPEED

    def update(self, *_):
        self.rect.x -= self.speed


class Coin(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.image = pygame.Surface((16, 16))
        self.image.fill(Config.COLOR_COIN)
        self.rect = self.image.get_rect(center=(x, y))


class Bullet(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.image = pygame.Surface((10, 10))
        self.image.fill(Config.COLOR_BULLET)
        self.rect = self.image.get_rect(center=(x, y))
        self.speed = Config.BULLET_SPEED

    def update(self, *_):
        self.rect.x += self.speed
        if self.rect.left > Config.SCREEN_W:
            self.kill()


# =========================
# 6) Game Engine
# =========================
class GameEngine:
    def __init__(self, shared: SharedState):
        pygame.init()
        self.screen = pygame.display.set_mode((Config.SCREEN_W, Config.SCREEN_H))
        pygame.display.set_caption("GestiX Runner (W1 Final)")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(None, 28)

        self.shared = shared
        self.recognizer = None  # will fetch from shared later

        self.game_state = "START"  # START, PLAYING, PAUSED, GAME_OVER
        self.speed_boost_until = 0

        # groups
        self.all_sprites = pygame.sprite.Group()
        self.platforms = pygame.sprite.Group()
        self.enemies = pygame.sprite.Group()
        self.coins = pygame.sprite.Group()
        self.bullets = pygame.sprite.Group()

        self.reset_game()
        self.enemy_spawn_timer=0

    def reset_game(self):
        # clear groups
        self.all_sprites.empty()
        self.platforms.empty()
        self.enemies.empty()
        self.coins.empty()
        self.bullets.empty()

        # player
        self.player = Player(50, Config.SCREEN_H - 50)
        self.all_sprites.add(self.player)

        # level blocks
        for i in range(30):
            p = Platform(i*50, Config.SCREEN_H - 40, 50, 40)
            self.platforms.add(p)
            self.all_sprites.add(p)

        p = Platform(200, Config.SCREEN_H - 120, 100, 20)
        self.platforms.add(p); self.all_sprites.add(p)

        for cx in (225, 250, 275):
            c = Coin(cx, Config.SCREEN_H - 150)
            self.coins.add(c); self.all_sprites.add(c)

        for ex in (400, 600):
            e = Enemy(ex, Config.SCREEN_H - 40)
            self.enemies.add(e); self.all_sprites.add(e)

        self.score = 0
        self.camera_offset_x = 0
        self.game_state = "START"
        self.speed_boost_until = 0
        self.enemy_spawn_timer=0

        # set eval off by default; will turn on when starting
        rec = self.shared.get_recognizer_ref()
        if rec: rec.set_expected_for_eval(None)

    # ---------- input ----------
    def handle_input(self):
        # gestures
        gesture = self.shared.get_gesture()
        action = Config.GESTURE_MAPPING.get(gesture, "NONE")

        if self.game_state == "START":
            if action == "START_GAME":  # Fist
                self.game_state = "PLAYING"
                rec = self.shared.get_recognizer_ref()
                if rec: rec.set_expected_for_eval("Open")  # example: evaluate "Open"

        elif self.game_state == "PLAYING":
            if action == "JUMP":
                self.player.jump()
            elif action == "SHOOT":
                self.player.shoot(self.bullets, self.all_sprites)
            elif action == "SPEED_UP":
                self.speed_boost_until = time.time() + 2.0
            elif action == "ULTI":
                # simple "clear screen"
                for e in list(self.enemies):
                    e.kill()
            elif action == "PAUSE_TOGGLE":
                self.game_state = "PAUSED"

        elif self.game_state == "PAUSED":
            if action == "PAUSE_TOGGLE":
                self.game_state = "PLAYING"

        elif self.game_state == "GAME_OVER":
            if action == "RESTART":  # ThumbUp
                self.reset_game()

        # keyboard (debug)
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.shared.set_running(False)
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    self.shared.set_running(False)
                if e.key == pygame.K_v:
                    self.print_validation_data()
                if e.key == pygame.K_1:
                    rec = self.shared.get_recognizer_ref()
                    if rec: rec.set_expected_for_eval("Open")
                if e.key == pygame.K_0:
                    rec = self.shared.get_recognizer_ref()
                    if rec: rec.set_expected_for_eval(None)

    # ---------- update ----------
    def update(self,dt):
        if self.game_state != "PLAYING":
            return

        # speed boost (OK gesture)
        speed_multiplier = 1.5 if time.time() < self.speed_boost_until else 1.0

        # update sprites
        self.all_sprites.update(self.platforms)

        # move enemies
        for e in self.enemies:
            e.update()

        #random add enemy
        self.enemy_spawn_timer+=dt
        if self.enemy_spawn_timer > np.random.uniform(1200, 2000): # 隨機生成障礙物，增加趣味性
            self.enemy_spawn_timer = 0
            h = np.random.randint(30, 60)
            w = np.random.randint(20, 35)
            e = Enemy(Config.SCREEN_W,Config.SCREEN_H - 40, w, h)
            self.enemies.add(e); self.all_sprites.add(e)

        # bullets vs enemies
        pygame.sprite.groupcollide(self.bullets, self.enemies, True, True)

        # player vs coins
        if pygame.sprite.spritecollide(self.player, self.coins, True):
            self.score += 10

        # player vs enemies
        hits = pygame.sprite.spritecollide(self.player, self.enemies, False)
        for enemy in hits:
            if self.player.vel_y > 0 and self.player.rect.bottom < enemy.rect.centery:
                enemy.kill(); self.score += 50; self.player.vel_y = -5
            else:
                self.game_state = "GAME_OVER"

        # camera follow (simple)
        target_scroll = self.player.rect.centerx - (Config.SCREEN_W / 3)
        if target_scroll > self.camera_offset_x:
            self.camera_offset_x = target_scroll * speed_multiplier

        # fall out
        if self.player.rect.top > Config.SCREEN_H:
            self.game_state = "GAME_OVER"

    # ---------- draw ----------
    def draw(self):
        self.screen.fill(Config.COLOR_SKY)

        # draw sprites with camera offset
        for spr in self.all_sprites:
            self.screen.blit(spr.image, (spr.rect.x - self.camera_offset_x, spr.rect.y))

        # HUD
        score_text = self.font.render(f"Score: {self.score}", True, Config.COLOR_TEXT)
        self.screen.blit(score_text, (10, 8))

        fps_text = self.font.render(f"FPS: {self.clock.get_fps():.1f}", True, Config.COLOR_TEXT)
        self.screen.blit(fps_text, (10, 32))

        # validation HUD
        rec = self.shared.get_recognizer_ref()
        if rec and rec.expected_for_eval:
            n, c, acc = rec.get_eval_stats()
            msg = f"[Eval:{rec.expected_for_eval}] {c}/{n}" + (f" ({acc:.1f}%)" if acc is not None else "")
            self.screen.blit(self.font.render(msg, True, Config.COLOR_TEXT), (10, 56))

        # overlays
        if self.game_state == "START":
            overlay = pygame.Surface((Config.SCREEN_W, Config.SCREEN_H), pygame.SRCALPHA)
            overlay.fill(Config.COLOR_UI_PAUSED)
            self.screen.blit(overlay, (0,0))
            t = self.font.render("Fist to START", True, (255,255,255))
            self.screen.blit(t, t.get_rect(center=(Config.SCREEN_W/2, Config.SCREEN_H/2)))

        elif self.game_state == "PAUSED":
            overlay = pygame.Surface((Config.SCREEN_W, Config.SCREEN_H), pygame.SRCALPHA)
            overlay.fill(Config.COLOR_UI_PAUSED)
            self.screen.blit(overlay, (0,0))
            t = self.font.render("PAUSED (Wave to Resume)", True, (255,255,255))
            self.screen.blit(t, t.get_rect(center=(Config.SCREEN_W/2, Config.SCREEN_H/2)))

        elif self.game_state == "GAME_OVER":
            overlay = pygame.Surface((Config.SCREEN_W, Config.SCREEN_H), pygame.SRCALPHA)
            overlay.fill((0,0,0,160))
            self.screen.blit(overlay, (0,0))
            t1 = self.font.render(f"GAME OVER! Score: {self.score}", True, (255,255,255))
            self.screen.blit(t1, t1.get_rect(center=(Config.SCREEN_W/2, Config.SCREEN_H/2 - 20)))
            t2 = self.font.render("ThumbUp to RESTART", True, (255,255,255))
            self.screen.blit(t2, t2.get_rect(center=(Config.SCREEN_W/2, Config.SCREEN_H/2 + 20)))

        pygame.display.flip()

    # ---------- validation print ----------
    def print_validation_data(self):
        cam = self.shared.get_camera_view()
        if cam and cam["landmarks"]:
            print("\n" + "="*60)
            print(f"LANDMARKS @ {time.time()}")
            for i, hand in enumerate(cam["landmarks"]):
                print(f"Hand {i+1} ({hand['handedness']}):")
                for j, (x,y,z) in enumerate(hand["landmarks"]):
                    print(f"  LM{j:02d}  x={x:.4f}  y={y:.4f}  z={z:.4f}")
            print("="*60 + "\n")
        else:
            print("[Validation] No landmark data available.")

    # ---------- main loop ----------
    def run(self):
        while self.shared.is_running():
            dt=self.clock.tick(Config.GAME_FPS)
            # fetch recognizer ref once ready
            if self.recognizer is None:
                self.recognizer = self.shared.get_recognizer_ref()

            self.handle_input()
            self.update(dt)
            self.draw()

            # show camera debug window (optional; reduce size)
            cam = self.shared.get_camera_view()
            if cam is not None:
                frame = cam["frame"]
                fps = cam["fps"]
                raw = cam["raw_gestures"]
                cv2.putText(frame, f"CamFPS:{fps:.1f}", (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)
                cv2.putText(frame, f"L:{raw['Left']}  R:{raw['Right']}", (10, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255,0,0), 2)
                small = cv2.resize(frame, (frame.shape[1]//2, frame.shape[0]//2))
                cv2.imshow("GestiX Camera (Debug)", small)
                if cv2.waitKey(1) & 0xFF == 27:
                    self.shared.set_running(False)

        pygame.quit()
        cv2.destroyAllWindows()


# =========================
# 7) Main
# =========================
def main():
    shared = SharedState()
    cam_thread = threading.Thread(target=camera_thread, args=(shared,), daemon=True)
    cam_thread.start()

    game = GameEngine(shared)
    game.run()

    cam_thread.join()
    print("Program finished.")

if __name__ == "__main__":
    main()
