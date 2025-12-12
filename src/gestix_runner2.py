# gestix_runner2.py
# GestiX Runner — Ninja Ink (Final, Kunai-only)
# - 視差捲動背景：多層山脈、雲霧、前景剪影
# - 程式化美術：自動生成水墨質感素材，無需外部圖檔
# - 視覺強化：漸層天空、地面紋理、光暈特效
# - 手勢控制來自 gestix_mediapipe2.SharedState / camera_thread
# - 最終整併：
#   (1) 只使用「苦無」武器，移除槍與槍袋
#   (2) 苦無投射物尺寸加大（外界與 BOSS 房一致）
#   (3) 進 BOSS 房不再清空子彈，與 boss_room 的「轉追蹤苦無」相容
#   (4) 玩家在 BOSS 房可正常受重力與操作（修正飄浮不能動）
#   (5) BOSS 房繪製順序修正：先畫宮殿與 Boss，再畫玩家與苦無
#   (6) 打贏 Boss 後玩家 HP 回滿
#   (7) 苦無拾取生成間隔預設縮短為 5 秒（可改 Config.KUNAI_SPAWN_TIME）
#   (8) Boss 房專用護盾時間 Config.BOSS_ULTI_DURATION
#   (9) Boss 房專用回血補包間隔 Config.HEAL_PACK_INTERVAL

import pygame, random, time, math, cv2
from collections import deque
from threading import Thread
from typing import Optional, Tuple, List

from gestix_mediapipe2 import SharedState, Config, camera_thread
from intro_screen import run_intro  # ★ 新增
from boss_room2 import BossRoom2
try:
    from boss_room import BossRoom
    HAS_BOSS = True
except Exception:
    HAS_BOSS = False


# ------------------ CONFIG DEFAULTS ------------------
def _ensure_config_defaults():
    defaults = dict(
        SCREEN_W=960,
        SCREEN_H=540,
        GAME_FPS=60,
        SCROLL_SPEED=5,
        GRAVITY=1.04,
        JUMP_VELOCITY=-17,
        GROUND_H=56,
        BULLET_SPEED=16,
        # 視覺色彩
        COLOR_SKY_TOP=(10, 15, 25),
        COLOR_SKY_BOT=(30, 40, 60),
        COLOR_GROUND=(20, 20, 25),
        COLOR_TEXT=(230, 230, 230),
        COLOR_BULLET=(255, 160, 60),
        # 護盾與查克拉
        ULTI_DURATION=10.0,
        BOSS_ULTI_DURATION=6.0,   # ★ BOSS 房專用大招時間（秒）
        COIN_ENERGY_GAIN=10,
        BOSS_SCORE_STEP=1000,
        MAX_BOSS_PHASE=5,
        # Boss 房回血補包生成間隔（秒）
        HEAL_PACK_INTERVAL=6.0,
        # 苦無生成（原世界拾取物）間隔（秒）→ 縮短
        KUNAI_SPAWN_TIME=5.0,
        # 苦無投擲冷卻（秒）
        KUNAI_COOLDOWN=0.5,
        # 苦無庫存上限（HUD 顯示也以此為準）
        KUNAI_MAX_STACK=10,
        # 生成物距離安全閾值
        SAFE_H_DIST=110,
        SAFE_V_DIST=80,
        SAFE_EUCL=150,
        # 手勢 mapping -> 動作
        GESTURE_MAPPING={
            "Fist": "START_GAME",
            "Open": "JUMP",
            "Point1": "PAUSE_TOGGLE",
            "Gun": "SHOOT",
            "ThumbUp": "PAUSE_TOGGLE",   # ★ ThumbUp 也能暫停/繼續
            "Victory": "JUMP",
            "OK": "NONE",
            "DualOpen": "ULTI",
        },
        # 玩家 HP
        MAX_HP=100,
    )
    for k, v in defaults.items():
        if not hasattr(Config, k):
            setattr(Config, k, v)

_ensure_config_defaults()


# ------------------ ASSET GENERATORS ------------------
def create_gradient_surface(w, h, c1, c2):
    surf = pygame.Surface((w, h))
    for y in range(h):
        r = c1[0] + (c2[0] - c1[0]) * y // h
        g = c1[1] + (c2[1] - c1[1]) * y // h
        b = c1[2] + (c2[2] - c1[2]) * y // h
        pygame.draw.line(surf, (r, g, b), (0, y), (w, y))
    return surf

def create_ink_mountain(w, h, color):
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    peak_x = random.randint(int(w * 0.3), int(w * 0.7))
    pygame.draw.polygon(surf, color, [(0, h), (w, h), (peak_x, 0)])
    return surf

def create_soft_cloud(radius, color):
    surf = pygame.Surface((radius * 3, radius * 2), pygame.SRCALPHA)
    pygame.draw.circle(surf, (*color, 180), (radius, radius), radius)
    pygame.draw.circle(surf, (*color, 180), (int(radius * 1.8), int(radius * 0.8)), int(radius * 0.8))
    pygame.draw.circle(surf, (*color, 180), (int(radius * 1.5), int(radius * 1.1)), int(radius * 0.7))
    return surf


# ------------------ VISUAL LAYERS ------------------
class ParallaxLayer:
    def __init__(self, scroll_factor, screen_w, item_generator, initial_count=3):
        self.factor = scroll_factor
        self.screen_w = screen_w
        self.items = []
        self.generator = item_generator
        for _ in range(initial_count):
            self.add_item(x_start=random.randint(0, screen_w))

    def add_item(self, x_start=None):
        if x_start is None:
            x_start = self.screen_w + random.randint(50, 200)
        item_data = self.generator()
        self.items.append({"surf": item_data["surf"], "x": float(x_start), "y": float(item_data["y"])})

    def update(self, base_speed):
        move = base_speed * self.factor
        for item in self.items:
            item["x"] -= move
        self.items = [i for i in self.items if i["x"] + i["surf"].get_width() > -100]
        if len(self.items) < 3 or (self.items and self.items[-1]["x"] < self.screen_w - 200):
            self.add_item()

    def draw(self, surf):
        for item in self.items:
            surf.blit(item["surf"], (int(item["x"]), int(item["y"])))


# ------------------ HELPERS ------------------
def rect_center(rect: pygame.Rect) -> Tuple[int, int]:
    return rect.centerx, rect.centery

def dist_ok(ax, ay, bx, by):
    dx, dy = abs(ax - bx), abs(ay - by)
    if dx < Config.SAFE_H_DIST:
        return False
    if dy < Config.SAFE_V_DIST:
        return False
    if (dx * dx + dy * dy) ** 0.5 < Config.SAFE_EUCL:
        return False
    return True

def _keep_apart(new_rect: pygame.Rect, others: List[pygame.Rect], pad: int) -> bool:
    a = new_rect.inflate(pad, pad)
    for o in others:
        if a.colliderect(o.inflate(pad, pad)):
            return False
    return True

def _push_right_until_safe(r: pygame.Rect, others: List[pygame.Rect], pad: int, limit_x: int) -> pygame.Rect:
    tries, step = 0, 32
    while not _keep_apart(r, others, pad) and tries < 24 and r.x < limit_x:
        r.x += step
        tries += 1
    return r


# ------------------ PARTICLES & EFFECTS ------------------
class Particle:
    def __init__(self, x, y, vx, vy, life, color, radius, fade=True, shape="circle"):
        self.x, self.y = float(x), float(y)
        self.vx, self.vy = float(vx), float(vy)
        self.life = float(life)
        self.t = 0.0
        self.color = color
        self.radius = radius
        self.fade = fade
        self.shape = shape

    def update(self, dt):
        self.t += dt
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.05
        return self.t < self.life

    def draw(self, surf):
        alpha = 255
        if self.fade:
            alpha = max(0, int(255 * (1 - self.t / self.life)))
        col = (*self.color[:3], alpha)
        s = pygame.Surface((self.radius * 2 + 2, self.radius * 2 + 2), pygame.SRCALPHA)
        if self.shape == "petal":
            pygame.draw.ellipse(s, col, (1, 1, self.radius * 2, int(self.radius * 1.2)))
        else:
            pygame.draw.circle(s, col, (self.radius + 1, self.radius + 1), self.radius)
        surf.blit(s, (int(self.x - self.radius), int(self.y - self.radius)), special_flags=pygame.BLEND_ALPHA_SDL2)

class PortalFX:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.t0 = time.time()

    def draw(self, surf):
        t = time.time() - self.t0
        r = 26 + int(6 * math.sin(t * 6))
        pygame.draw.circle(surf, (120, 200, 255), (int(self.x), int(self.y)), r, 2)
        for i in range(3):
            ang = math.radians(t * 260 + i * 120)
            ox = int(self.x + math.cos(ang) * r)
            oy = int(self.y + math.sin(ang) * r)
            pygame.draw.circle(surf, (180, 240, 255), (ox, oy), 5)
        glow = pygame.Surface((r * 2 + 24, r * 2 + 24), pygame.SRCALPHA)
        pygame.draw.circle(glow, (80, 160, 255, 70), (r + 12, r + 12), r + 10)
        surf.blit(glow, (int(self.x - r - 12), int(self.y - r - 12)), special_flags=pygame.BLEND_ADD)


# ------------------ ENTITIES ------------------
class Player(pygame.sprite.Sprite):
    def __init__(self, x, ground_y):
        super().__init__()
        self.rect = pygame.Rect(x, ground_y - 116, 58, 116)
        self.vel_y = 0.0
        self.on_ground = True
        self.air_jumps_left = 1
        self.anim_timer = 0.0
        self.anim_index = 0
        self.anim_speed = 0.1
        self.horizontal_boost = 0.0
        self.base_x = x
        self.max_forward = 190

        # 舊槍系統變數保留但不使用
        self.has_gun = False
        self.bullets_left = 0
        self.gun_expire_ts = 0.0

        self.prev_rect = self.rect.copy()
        self.trail = deque(maxlen=6)

        # HP 與苦無
        self.max_hp = getattr(Config, "MAX_HP", 100)
        self.hp = self.max_hp
        self._last_kunai_ts = 0.0
        self.kunai_stack = 0
        self.kunai_max = getattr(Config, "KUNAI_MAX_STACK", 10)
        self.kunai_count = self.kunai_stack  # 別名相容

        # 會在 GameEngine.update() 鏡射
        self.shield_on = False

    def _push_trail(self):
        self.trail.append((self.rect.copy(), time.time()))

    def draw_ninja(self, surf: pygame.Surface):
        now = time.time()
        for r, t0 in self.trail:
            age = now - t0
            if age > 0.25:
                continue
            alpha = max(0, 110 - int(age * 420))
            ghost = pygame.Surface((r.width, r.height), pygame.SRCALPHA)
            pygame.draw.rect(ghost, (70, 80, 110, alpha), (0, 0, r.width, r.height), border_radius=8)
            surf.blit(ghost, r.topleft)

        x, y, w, h = self.rect

        sh = pygame.Surface((max(50, w // 2), 12), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 95), (0, 0, max(50, w // 2), 12))
        surf.blit(sh, (self.rect.centerx - max(25, w // 4), self.rect.bottom - 6))

        t = time.time()
        flutter = int(6 * math.sin(t * 10))
        pygame.draw.polygon(surf, (220, 50, 60), [(x + 12, y + 20), (x - 22, y + 15 + flutter), (x - 6, y + 26 + flutter)])
        pygame.draw.rect(surf, (24, 26, 36), (x + 14, y + 4, w - 28, 24), border_radius=6)
        pygame.draw.rect(surf, (230, 235, 255), (x + w // 2 - 10, y + 10, 20, 5))
        pygame.draw.rect(surf, (28, 30, 44), (x + 6, y + 30, 18, 12), border_radius=6)
        pygame.draw.rect(surf, (28, 30, 44), (x + w - 24, y + 30, 18, 12), border_radius=6)
        torso_rect = (x + 8, y + 40, w - 16, 44)
        pygame.draw.rect(surf, (34, 38, 54), torso_rect, border_radius=8)
        pygame.draw.line(surf, (70, 90, 140), (x + 12, y + 48), (x + w - 12, y + 48), 2)
        pygame.draw.line(surf, (50, 65, 100), (x + 12, y + 58), (x + w - 12, y + 58), 2)
        pygame.draw.rect(surf, (90, 30, 38), (x + 10, y + 86, w - 20, 6), border_radius=3)
        pygame.draw.rect(surf, (34, 38, 54), (x + 2, y + 58, 14, 16), border_radius=4)
        pygame.draw.rect(surf, (34, 38, 54), (x + w - 16, y + 58, 14, 16), border_radius=4)
        leg_a, leg_b = (52, 58, 96), (44, 50, 84)
        c1 = leg_a if self.anim_index == 0 else leg_b
        c2 = leg_b if self.anim_index == 0 else leg_a
        pygame.draw.rect(surf, c1, (x + 8, y + 96, 18, 34), border_radius=6)
        pygame.draw.rect(surf, c2, (x + w - 26, y + 96, 18, 34), border_radius=6)
        pygame.draw.rect(surf, (140, 100, 70), (x + 6, y + h - 12, 22, 10), border_radius=4)
        pygame.draw.rect(surf, (140, 100, 70), (x + w - 28, y + h - 12, 22, 10), border_radius=4)

    def update(self, dt_ms, ground_y, state, particles: List['Particle']):
        self.prev_rect = self.rect.copy()

        if state not in ("PLAYING", "BOSS_ROOM"):
            return

        if not self.on_ground:
            self.vel_y += Config.GRAVITY
            self.rect.y += int(self.vel_y)
            if self.horizontal_boost > 0:
                self.rect.x += int(self.horizontal_boost)
                self.rect.x = min(self.rect.x, self.base_x + self.max_forward)
                self.horizontal_boost *= 0.94

        if self.rect.bottom >= ground_y:
            self.rect.bottom = ground_y
            if not self.on_ground and state == "PLAYING":
                spawn_landing_dust(particles, self.rect.centerx, ground_y - 3)
                self.air_jumps_left = 1
            self.vel_y = 0.0
            self.on_ground = True
        else:
            self.on_ground = False

        if self.on_ground and self.rect.x > self.base_x:
            self.rect.x -= min(3, self.rect.x - self.base_x)

        self.anim_timer += dt_ms / 1000.0
        if self.anim_timer >= self.anim_speed:
            self.anim_timer = 0.0
            self.anim_index = (self.anim_index + 1) % 2
            self._push_trail()

    def jump(self):
        if self.on_ground:
            self.vel_y = Config.JUMP_VELOCITY - 4.0
            self.horizontal_boost = 7.2
            self.on_ground = False
        elif self.air_jumps_left > 0:
            self.vel_y = Config.JUMP_VELOCITY - 4.0
            self.horizontal_boost = 6.2
            self.air_jumps_left -= 1

    def shoot_kunai(self, bullets, all_sprites):
        now = time.time()
        if self.kunai_stack <= 0:
            return
        if now - self._last_kunai_ts < float(getattr(Config, "KUNAI_COOLDOWN", 0.5)):
            return
        k = Kunai(self.rect.right + 8, self.rect.centery)
        bullets.add(k)
        if all_sprites is not None:
            all_sprites.add(k)
        self._last_kunai_ts = now
        self.kunai_stack = max(0, self.kunai_stack - 1)
        self.kunai_count = self.kunai_stack

    def land_on(self, top_y):
        self.rect.bottom = top_y
        self.vel_y = 0.0
        self.on_ground = True
        self.air_jumps_left = 1
        self.horizontal_boost = max(self.horizontal_boost * 0.6, 0.0)


class Kunai(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.rect = pygame.Rect(x, y - 6, 36, 12)  # 36x12
        self.speed = Config.BULLET_SPEED

    def update(self, _):
        self.rect.x += self.speed
        if self.rect.left > Config.SCREEN_W + 60:
            self.kill()

    def draw(self, surf):
        x, y, w, h = self.rect
        blade = pygame.Surface((w + 12, h + 8), pygame.SRCALPHA)
        pygame.draw.polygon(blade, (210, 210, 220), [(0, h // 2 + 4), (18, 0), (18, h + 8)])
        pygame.draw.rect(blade, (70, 70, 90), (18, 2, w - 10, h + 4), border_radius=3)
        surf.blit(blade, (x - 6, y - 4))


class KunaiPickup(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.rect = pygame.Rect(0, 0, 26, 10)
        self.rect.center = (x, y)
        self.speed = Config.SCROLL_SPEED

    def update(self, _):
        self.rect.x -= self.speed
        if self.rect.right < -40:
            self.kill()

    def draw(self, surf):
        x, y, w, h = self.rect
        t = time.time()
        glow = pygame.Surface((w + 56, h + 56), pygame.SRCALPHA)
        cx, cy = (w + 56) // 2, (h + 56) // 2
        for r, alpha in [(30, 65), (22, 95), (16, 120), (10, 150)]:
            pygame.draw.circle(glow, (255, 230, 160, alpha), (cx, cy), r)
        surf.blit(glow, (x - 28, y - 28), special_flags=pygame.BLEND_ADD)

        twinkle = pygame.Surface((70, 70), pygame.SRCALPHA)
        pygame.draw.line(twinkle, (255, 245, 220, 110), (35, 0), (35, 70), 2)
        pygame.draw.line(twinkle, (255, 245, 220, 110), (0, 35), (70, 35), 2)
        ang = (t * 120) % 360
        twinkle = pygame.transform.rotozoom(twinkle, ang, 1.0)
        rect = twinkle.get_rect(center=(x + w // 2, y + h // 2))
        surf.blit(twinkle, rect.topleft, special_flags=pygame.BLEND_ADD)

        blade = pygame.Surface((w + 8, h + 6), pygame.SRCALPHA)
        pygame.draw.polygon(blade, (220, 220, 230), [(0, h // 2 + 3), (14, 0), (14, h + 6)])
        pygame.draw.rect(blade, (60, 60, 80), (14, 2, w - 6, h + 2), border_radius=2)
        surf.blit(blade, (x - 4, y - 3))


class Coin(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.rect = pygame.Rect(0, 0, 30, 30)
        self.rect.center = (x, y)
        self.speed = Config.SCROLL_SPEED
        self.anim = 0.0

    def update(self, _):
        self.rect.x -= self.speed
        if self.rect.right < -40:
            self.kill()
        self.anim += 0.1

    def draw(self, surf):
        cx, cy = self.rect.center
        glow_size = 40 + int(5 * math.sin(self.anim))
        glow = pygame.Surface((glow_size, glow_size), pygame.SRCALPHA)
        pygame.draw.circle(glow, (180, 220, 255, 60), (glow_size // 2, glow_size // 2), glow_size // 2)
        surf.blit(glow, (cx - glow_size // 2, cy - glow_size // 2), special_flags=pygame.BLEND_ADD)
        pygame.draw.circle(surf, (200, 240, 255), (cx, cy), 12, 2)
        pygame.draw.circle(surf, (255, 255, 255), (cx, cy), 7)


class Obstacle(pygame.sprite.Sprite):
    def __init__(self, x, ground_y, air, scale):
        super().__init__()
        h = random.randint(60, 200)
        w = random.randint(50, 90)
        yb = ground_y - (220 + random.randint(0, 80)) if air else ground_y
        self.rect = pygame.Rect(x, yb - h, w, h)
        self.speed = int(Config.SCROLL_SPEED * (1.0 + 0.22 * scale))
        self.texture = pygame.Surface((w, h), pygame.SRCALPHA)
        self.texture.fill((40, 40, 50))
        pygame.draw.rect(self.texture, (60, 60, 75), (0, 0, w, h), 2)
        for _ in range(3):
            rx, ry = random.randint(10, w - 10), random.randint(10, h - 10)
            rw, rh = random.randint(4, 10), random.randint(4, 20)
            pygame.draw.rect(self.texture, (30, 30, 35), (rx, ry, rw, rh))

    def update(self, _):
        self.rect.x -= self.speed
        if self.rect.right < -60:
            self.kill()

    def draw(self, surf):
        surf.blit(self.texture, self.rect.topleft)


class Silhouette(pygame.sprite.Sprite):
    def __init__(self, kind, x, ground_y, speed):
        super().__init__()
        self.kind = kind
        self.x = float(x)
        self.ground_y = ground_y
        self.speed = speed
        self.image = pygame.Surface((100, 200), pygame.SRCALPHA)
        col = (15, 15, 20)
        if kind == "pagoda":
            pygame.draw.rect(self.image, col, (20, 130, 60, 70))
            pygame.draw.polygon(self.image, col, [(10, 130), (90, 130), (50, 100)])
            pygame.draw.polygon(self.image, col, [(15, 100), (85, 100), (50, 70)])
        else:
            pygame.draw.rect(self.image, col, (20, 120, 10, 80))
            pygame.draw.rect(self.image, col, (70, 120, 10, 80))
            pygame.draw.rect(self.image, col, (10, 130, 80, 10))
            pygame.draw.rect(self.image, col, (15, 110, 70, 8))

    def update(self):
        self.x -= self.speed
        return self.x > -150

    def draw(self, surf):
        surf.blit(self.image, (int(self.x), self.ground_y - 200))


# ------------------ GAME ENGINE ------------------
def spawn_coin_sparkles(particles: List[Particle], x, y):
    for _ in range(5):
        ang = random.uniform(0, 2 * math.pi)
        spd = random.uniform(1.5, 3.0)
        particles.append(Particle(x, y, math.cos(ang) * spd, math.sin(ang) * spd, 0.55, (255, 192, 203), 4, shape="petal"))
    for _ in range(6):
        ang = random.uniform(0, 2 * math.pi)
        spd = random.uniform(2.0, 3.6)
        particles.append(Particle(x, y, math.cos(ang) * spd, math.sin(ang) * spd, 0.45, (255, 255, 150), 3))

def spawn_landing_dust(particles: List[Particle], x, y):
    for _ in range(8):
        vx = random.uniform(-2.4, 2.4)
        vy = random.uniform(-1.6, -0.3)
        particles.append(Particle(x + random.uniform(-10, 10), y, vx, vy, 0.5, (120, 105, 95), 3))

def spawn_bullet_smoke(particles: List[Particle], x, y):
    for _ in range(8):
        ang = random.uniform(0, 2 * math.pi)
        spd = random.uniform(1.0, 2.4)
        particles.append(Particle(x, y, math.cos(ang) * spd, math.sin(ang) * spd, 0.5, (200, 200, 200), 4))


class GameEngine:
    def __init__(self, shared: SharedState):
        pygame.init()
        self.screen = pygame.display.set_mode((Config.SCREEN_W, Config.SCREEN_H))
        pygame.display.set_caption("GestiX Runner — Ninja Ink (Final, Kunai-only)")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 24)
        self.big_font = pygame.font.SysFont("arial", 52, bold=True)
        self.shared = shared
        self.ground_y = Config.SCREEN_H - Config.GROUND_H

        self.bg_gradient = create_gradient_surface(Config.SCREEN_W, Config.SCREEN_H, Config.COLOR_SKY_TOP, Config.COLOR_SKY_BOT)

        self._init_parallax_layers()

        self.all_sprites = pygame.sprite.Group()
        self.coins = pygame.sprite.Group()
        self.obstacles = pygame.sprite.Group()
        self.bullets = pygame.sprite.Group()
        self.kunai_items = pygame.sprite.Group()
        self.particles: List[Particle] = []

        self.reset_game()
        self._paused_from = "PLAYING"

    def _init_parallax_layers(self):
        def gen_far_mountain():
            w = random.randint(250, 400)
            h = random.randint(150, 250)
            s = create_ink_mountain(w, h, (25, 30, 40, 180))
            return {"surf": s, "y": self.ground_y - h + 20, "w": w}
        self.layer_far = ParallaxLayer(0.2, Config.SCREEN_W, gen_far_mountain, initial_count=3)

        def gen_mid_cloud():
            sz = random.randint(20, 40)
            s = create_soft_cloud(sz, (200, 200, 210))
            y = random.randint(50, 200)
            return {"surf": s, "y": y, "w": sz * 3}
        self.layer_mid = ParallaxLayer(0.5, Config.SCREEN_W, gen_mid_cloud, initial_count=5)

        self.silhouettes: List[Silhouette] = []

    def reset_game(self):
        self.all_sprites.empty()
        self.coins.empty()
        self.obstacles.empty()
        self.bullets.empty()
        self.kunai_items.empty()
        self.particles.clear()

        self.player = Player(140, self.ground_y)
        self.all_sprites.add(self.player)

        self.score = 0
        self.energy = 0
        self.shield_on = False
        self.shield_until = 0.0

        self.start_time = time.time()
        self._last_score_t = time.time()
        self._obs_cd_until = 0.0
        self._coin_cd_until = 0.0
        self._kunai_cd_until = 0.0

        self.game_state = "START"
        self.silhouettes = [Silhouette("torii", 600, self.ground_y, Config.SCROLL_SPEED * 0.8)]

        self.boss_room = None
        self.portal_fx = None
        self._portal_spawn_ts = 0.0
        self._boss_triggered = False
        self.boss_phase = 0

    def difficulty(self):
        return min(3.0, (time.time() - self.start_time) / 28.0)

    def poll_gesture_action(self):
        return Config.GESTURE_MAPPING.get(self.shared.get_gesture(), "NONE")

    def _entities(self):
        return list(self.obstacles) + list(self.coins) + list(self.kunai_items)

    def _safe_xy(self, y_ground, y_air):
        entities = self._entities()
        for _ in range(26):
            x = Config.SCREEN_W + random.randint(40, 140)
            y = random.choice([y_ground, y_air])
            ok = True
            for e in entities:
                ex, ey = rect_center(e.rect)
                if not dist_ok(x, y, ex, ey):
                    ok = False
                    break
            if ok:
                return x, y
        return Config.SCREEN_W + 220, y_ground

    def _safe_place_rect(self, r: pygame.Rect, pad: int) -> pygame.Rect:
        others = [e.rect for e in self.obstacles] + [e.rect for e in self.coins] + [e.rect for e in self.kunai_items]
        if _keep_apart(r, others, pad):
            return r
        return _push_right_until_safe(r, others, pad, Config.SCREEN_W + 800)

    def _rightmost_obstacle_x(self) -> Optional[int]:
        xs = [o.rect.right for o in self.obstacles]
        return max(xs) if xs else None

    def spawn_obstacle_if_needed(self):
        now = time.time()
        if now < self._obs_cd_until:
            return
        d = self.difficulty()
        min_gap = 380 - int(28 * d)
        rightmost = self._rightmost_obstacle_x()
        if rightmost and rightmost > Config.SCREEN_W - min_gap:
            return
        self._obs_cd_until = now + max(1.0, 1.45 - 0.14 * d)
        air_prob = 0.32 + 0.1 * d
        is_air = random.random() < air_prob
        x, _ = self._safe_xy(self.ground_y - 10, self.ground_y - 220)
        o = Obstacle(x, self.ground_y, is_air, d)
        o.rect = self._safe_place_rect(o.rect, pad=26)
        self.obstacles.add(o)
        self.all_sprites.add(o)
        if random.random() < 0.2:
            kind = random.choice(["pagoda", "torii"])
            self.silhouettes.append(Silhouette(kind, Config.SCREEN_W + 160, self.ground_y, Config.SCROLL_SPEED * 0.8))

    def spawn_coin_if_needed(self):
        now = time.time()
        if now < self._coin_cd_until:
            return
        self._coin_cd_until = now + random.uniform(0.95, 1.5)
        y_ground = self.ground_y - 26
        y_air = self.ground_y - 160
        x, y = self._safe_xy(y_ground, y_air)
        c = Coin(x, y)
        c.rect = self._safe_place_rect(c.rect, pad=32)
        self.coins.add(c)
        self.all_sprites.add(c)

    def spawn_kunai_if_needed(self):
        now = time.time()
        if now < self._kunai_cd_until:
            return
        self._kunai_cd_until = now + float(getattr(Config, "KUNAI_SPAWN_TIME", 5.0))
        y_air = self.ground_y - (160 + random.randint(-30, 40))
        x, _ = self._safe_xy(self.ground_y - 10, y_air)
        k = KunaiPickup(x, y_air)
        k.rect = self._safe_place_rect(k.rect, pad=24)
        self.kunai_items.add(k)
        self.all_sprites.add(k)

    def _update_scoring(self):
        if time.time() - self._last_score_t >= 1.0:
            self.score += 20
            self._last_score_t = time.time()

    def _update_shield(self):
        if self.shield_on and time.time() > self.shield_until:
            self.shield_on = False

    @staticmethod
    def _intersection_area(a, b):
        if not a.colliderect(b):
            return 0
        x1 = max(a.left, b.left); y1 = max(a.top, b.top)
        x2 = min(a.right, b.right); y2 = min(a.bottom, b.bottom)
        return max(0, x2 - x1) * max(0, y2 - y1)

    def _handle_collisions(self):
        for c in pygame.sprite.spritecollide(self.player, self.coins, dokill=True):
            self.score += 20
            self.energy = min(100, self.energy + Config.COIN_ENERGY_GAIN)
            spawn_coin_sparkles(self.particles, c.rect.centerx, c.rect.centery)

        if pygame.sprite.spritecollide(self.player, self.kunai_items, dokill=True):
            self.player.kunai_stack = min(self.player.kunai_max, self.player.kunai_stack + 1)
            self.player.kunai_count = self.player.kunai_stack

        hits = pygame.sprite.groupcollide(self.bullets, self.obstacles, True, True)
        for _ in hits.values():
            spawn_bullet_smoke(self.particles, self.player.rect.centerx + 100, self.player.rect.centery - 30)
            self.score += 50

        for ob in self.obstacles:
            pbox = self.player.rect.inflate(-8, -8)
            obox = ob.rect.inflate(-4, -4)
            if not pbox.colliderect(obox):
                continue
            prev_bottom = self.player.prev_rect.bottom
            falling = self.player.vel_y >= 0
            if falling and prev_bottom <= obox.top - 2:
                self.player.land_on(obox.top)
                continue
            inter = self._intersection_area(pbox, obox)
            min_a = min(pbox.width * pbox.height, obox.width * obox.height)
            if inter >= 0.35 * min_a:
                if self.shield_on:
                    ob.kill()
                    self.score += 50
                else:
                    self.player.hp -= 20
                    ob.kill()
                    if self.player.hp <= 0:
                        self.game_state = "GAME_OVER"
                        return

    def update(self, dt):
        if self.game_state == "PLAYING":
            self._update_scoring()
            self.spawn_obstacle_if_needed()
            self.spawn_coin_if_needed()
            self.spawn_kunai_if_needed()

            self.layer_far.update(Config.SCROLL_SPEED)
            self.layer_mid.update(Config.SCROLL_SPEED)

            for s in list(self.all_sprites):
                if isinstance(s, Player):
                    s.update(dt, self.ground_y, self.game_state, self.particles)
                else:
                    s.update(dt)

            self.particles = [p for p in self.particles if p.update(dt / 1000.0)]

            self._update_shield()
            self._handle_collisions()

            if HAS_BOSS and (not self._boss_triggered):
                target_score = getattr(Config, "BOSS_SCORE_STEP", 1000) * (self.boss_phase + 1)
                if self.boss_phase < getattr(Config, "MAX_BOSS_PHASE", 5) and self.score >= target_score:
                    if self.portal_fx is None:
                        self.portal_fx = PortalFX(Config.SCREEN_W - 120, self.ground_y - 60)
                        self._portal_spawn_ts = time.time()

            if self.portal_fx is not None:
                dx = abs(self.player.rect.centerx - self.portal_fx.x)
                dy = abs(self.player.rect.centery - self.portal_fx.y)
                near = (dx < 40 and dy < 80)
                timeout = (time.time() - self._portal_spawn_ts) > 2.0
                if near or timeout:
                    self.game_state = "BOSS_ROOM"

                    # 根據 boss_phase 決定進哪個 Boss 房
                    if self.boss_phase == 0:
                        self.boss_room = BossRoom(self.player, self.shared, self.bullets)
                    elif self.boss_phase == 1:
                        self.boss_room = BossRoom2(self.player, self.shared, self.bullets)

                    self.portal_fx = None
                    self._boss_triggered = True


            self.player.shield_on = self.shield_on

        elif self.game_state == "BOSS_ROOM" and HAS_BOSS and self.boss_room:
            self.player.update(dt, self.ground_y, self.game_state, self.particles)
            self.boss_room.update(dt)
            self._update_shield()
            self.player.shield_on = self.shield_on

            if self.player.hp <= 0:
                self.game_state = "GAME_OVER"
                return

            if self.boss_room.is_boss_dead():
                self.player.hp = self.player.max_hp
                self.boss_room = None
                self.game_state = "PLAYING"
                self.portal_fx = None
                self._portal_spawn_ts = 0.0
                self.boss_phase += 1
                self._boss_triggered = False

    def _draw_ground_pretty(self):
        pygame.draw.rect(self.screen, Config.COLOR_GROUND, (0, self.ground_y, Config.SCREEN_W, Config.GROUND_H))
        pygame.draw.line(self.screen, (150, 205, 255), (0, self.ground_y), (Config.SCREEN_W, self.ground_y), 2)
        pygame.draw.rect(self.screen, (32, 48, 64), (0, self.ground_y + 2, Config.SCREEN_W, 14))
        t = time.time()
        sway = math.sin(t * 3.0) * 2.0
        blade_color = (42, 72, 90)
        for x in range(0, Config.SCREEN_W, 20):
            base = self.ground_y + 12
            h = 10 + (x // 20) % 6
            px = x + int(sway * ((x // 20) % 3 - 1))
            pygame.draw.polygon(self.screen, blade_color, [(px, base), (px + 4, base), (px + 2, base - h)])
        for i in range(2):
            y = self.ground_y + 18 + i * 10
            pygame.draw.line(self.screen, (36, 54, 66), (0, y), (Config.SCREEN_W, y), 2)

    def _draw_background_world(self):
        self.screen.blit(self.bg_gradient, (0, 0))
        mx, my = int(Config.SCREEN_W * 0.78), 90
        halo = pygame.Surface((120, 120), pygame.SRCALPHA)
        pygame.draw.circle(halo, (150, 40, 40, 40), (60, 60), 60)
        self.screen.blit(halo, (mx - 60, my - 60), special_flags=pygame.BLEND_ADD)
        pygame.draw.circle(self.screen, (200, 55, 55), (mx, my), 30)

        self.layer_far.draw(self.screen)
        self.layer_mid.draw(self.screen)

        for s in list(self.silhouettes):
            if not s.update():
                self.silhouettes.remove(s)
            else:
                s.draw(self.screen)

        self._draw_ground_pretty()

    def _draw_hud(self):
        t = self.font.render(f"Score: {int(self.score)}", True, Config.COLOR_TEXT)
        self.screen.blit(t, (Config.SCREEN_W - t.get_width() - 14, 10))

        BAR_W, BAR_H = 200, 18
        BX, BY = 14, 12
        lbl = self.font.render("Chakra", True, (200, 200, 220))
        self.screen.blit(lbl, (BX, BY - 6))
        frame_y = BY + lbl.get_height() - 10
        pygame.draw.rect(self.screen, (60, 60, 70), (BX, frame_y, BAR_W, BAR_H), 2)
        fill_w = int(BAR_W * (self.energy / 100.0))
        pygame.draw.rect(self.screen, (100, 200, 255), (BX + 2, frame_y + 2, max(0, fill_w - 2), BAR_H - 3))

        HP_W, HP_H = 200, 14
        HX, HY = 14, frame_y + BAR_H + 10
        pygame.draw.rect(self.screen, (60, 60, 70), (HX, HY, HP_W, HP_H), 2, border_radius=4)
        hp_ratio = max(0.0, min(1.0, self.player.hp / float(self.player.max_hp)))
        hp_fill = int((HP_W - 4) * hp_ratio)
        pygame.draw.rect(self.screen, (120, 220, 160), (HX + 2, HY + 2, hp_fill, HP_H - 4), border_radius=3)
        hp_txt = self.font.render(f"HP {max(0, self.player.hp)}/{self.player.max_hp}", True, (210, 220, 210))
        self.screen.blit(hp_txt, (HX + HP_W + 10, HY - 6))

        SCORE_W, SCORE_H = 200, 12
        SX, SY = 14, HY + HP_H + 10
        pygame.draw.rect(self.screen, (60, 60, 70), (SX, SY, SCORE_W, SCORE_H), 2, border_radius=4)
        ratio = (self.score % 1000) / 1000.0
        fill_w = int((SCORE_W - 4) * ratio)
        pygame.draw.rect(self.screen, (255, 215, 120), (SX + 2, SY + 2, fill_w, SCORE_H - 4), border_radius=3)
        score_txt = self.font.render(f"Score {int(self.score)}", True, (255, 235, 200))
        self.screen.blit(score_txt, (SX + SCORE_W + 10, SY - 6))

        k_text = self.font.render(f"Kunai x {self.player.kunai_stack}/{getattr(Config, 'KUNAI_MAX_STACK', 10)}", True, (220, 220, 240))
        self.screen.blit(k_text, (14, SY + SCORE_H + 8))

        fps_text = self.font.render(f"FPS: {self.clock.get_fps():.1f}", True, Config.COLOR_TEXT)
        self.screen.blit(fps_text, (Config.SCREEN_W - fps_text.get_width() - 14, 36))

    def _draw_shield(self):
        if not self.shield_on:
            return
        px, py = self.player.rect.center
        radius = 72
        t = time.time()
        alpha = 85 + int(45 * (0.5 + 0.5 * math.sin(t * 7)))
        halo = pygame.Surface((radius * 2 + 10, radius * 2 + 10), pygame.SRCALPHA)
        pygame.draw.circle(halo, (100, 200, 255, alpha), (radius + 5, radius + 5), radius, 3)
        self.screen.blit(halo, (px - radius - 5, py - radius - 5), special_flags=pygame.BLEND_ADD)

    def draw(self):
        if self.game_state == "BOSS_ROOM" and HAS_BOSS and self.boss_room:
            self.boss_room.draw(self.screen)
        else:
            self._draw_background_world()
            for o in self.obstacles: o.draw(self.screen)
            for c in self.coins: c.draw(self.screen)
            for k in self.kunai_items: k.draw(self.screen)
            if getattr(self, "portal_fx", None):
                self.portal_fx.draw(self.screen)

        for b in self.bullets:
            if hasattr(b, "draw"):
                b.draw(self.screen)
            else:
                pygame.draw.rect(self.screen, (255, 255, 255), b.rect)

        self.player.draw_ninja(self.screen)

        for p in self.particles:
            p.draw(self.screen)

        self._draw_shield()
        self._draw_hud()

        if self.game_state == "START":
            overlay = pygame.Surface((Config.SCREEN_W, Config.SCREEN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 150))
            self.screen.blit(overlay, (0, 0))
            t = self.big_font.render("Fist to START", True, (255, 255, 255))
            self.screen.blit(t, t.get_rect(center=(Config.SCREEN_W / 2, Config.SCREEN_H / 2)))

        elif self.game_state == "PAUSED":
            overlay = pygame.Surface((Config.SCREEN_W, Config.SCREEN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 120))
            self.screen.blit(overlay, (0, 0))
            t = self.big_font.render("PAUSED", True, (255, 255, 255))
            self.screen.blit(t, t.get_rect(center=(Config.SCREEN_W / 2, Config.SCREEN_H / 2)))

        elif self.game_state == "GAME_OVER":
            overlay = pygame.Surface((Config.SCREEN_W, Config.SCREEN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 140))
            self.screen.blit(overlay, (0, 0))
            t1 = self.big_font.render(f"GAME OVER: {int(self.score)}", True, (255, 100, 100))
            t2 = self.big_font.render("ThumbUp to RESTART", True, (220, 220, 220))
            self.screen.blit(t1, t1.get_rect(center=(Config.SCREEN_W / 2, Config.SCREEN_H / 2 - 24)))
            self.screen.blit(t2, t2.get_rect(center=(Config.SCREEN_W / 2, Config.SCREEN_H / 2 + 32)))

        pygame.display.flip()

    # ✅ 這裡是你最需要的：完整修好的狀態機 run()
    def run(self):
        while self.shared.is_running():
            dt = self.clock.tick(Config.GAME_FPS)

            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.shared.set_running(False)

            action = self.poll_gesture_action()

            # ---------- STATE MACHINE ----------
            if self.game_state == "START":
                if action == "START_GAME":
                    self.game_state = "PLAYING"
                    self.start_time = time.time()
                    self._last_score_t = time.time()

            elif self.game_state == "PLAYING":
                if action == "PAUSE_TOGGLE":
                    self._paused_from = "PLAYING"
                    self.game_state = "PAUSED"
                elif action == "JUMP":
                    self.player.jump()
                elif action == "SHOOT":
                    self.player.shoot_kunai(self.bullets, self.all_sprites)
                elif action == "ULTI":
                    if (not self.shield_on) and self.energy >= 100:
                        self.shield_on = True
                        self.shield_until = time.time() + float(getattr(Config, "ULTI_DURATION", 10.0))
                        self.energy = 0

            elif self.game_state == "BOSS_ROOM" and HAS_BOSS and self.boss_room:
                if action == "PAUSE_TOGGLE":
                    self._paused_from = "BOSS_ROOM"
                    self.game_state = "PAUSED"
                elif action == "JUMP":
                    self.player.jump()
                elif action == "SHOOT":
                    self.player.shoot_kunai(self.boss_room.bullets, None)
                elif action == "ULTI":
                    if (not self.shield_on) and self.energy >= 100:
                        self.shield_on = True
                        dur = float(getattr(Config, "BOSS_ULTI_DURATION", getattr(Config, "ULTI_DURATION", 10.0)))
                        self.shield_until = time.time() + dur
                        self.energy = 0

            elif self.game_state == "PAUSED":
                if action == "PAUSE_TOGGLE":
                    self.game_state = self._paused_from
                    self._paused_from = "PLAYING"

            elif self.game_state == "GAME_OVER":
                # 你原本用 RESTART，但 mapping 沒有這個，所以改成 ThumbUp / Fist 都能重開
                if action in ("START_GAME", "PAUSE_TOGGLE"):
                    self.reset_game()

            # ---------- PER-FRAME UPDATE/DRAW ----------
            if self.game_state != "PAUSED":
                self.update(dt)
            self.draw()

            # ---------- CAMERA DEBUG WINDOW ----------
            cam = self.shared.get_camera_view()
            if cam is not None:
                frame = cam["frame"]
                fps = cam["fps"]
                raw = cam["raw_gestures"]
                cv2.putText(frame, f"CamFPS:{fps:.1f}", (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                cv2.putText(frame, f"L:{raw['Left']}  R:{raw['Right']}", (10, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
                recog = self.shared.get_recognizer_ref()
                if recog is not None:
                    n, cur_g, correct, acc = recog.get_acc()
                    cv2.putText(frame, f"Acc({cur_g}): {acc:.1f}% ({correct}/{n})", (10, 84), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

                small = cv2.resize(frame, (frame.shape[1] // 2, frame.shape[0] // 2))
                cv2.imshow("GestiX Camera (Debug)", small)

                # ESC 退出：一定要在 while 外統一 quit
                if cv2.waitKey(1) & 0xFF == 27:
                    self.shared.set_running(False)

        pygame.quit()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    shared = SharedState()
    t = Thread(target=camera_thread, args=(shared,), daemon=True)
    t.start()

    run_intro(shared)
    GameEngine(shared).run()
    t.join()
