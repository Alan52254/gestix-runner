# gestix_runner2.py
# GestiX Runner — Ninja Ink (Visual Upgrade)
# - 視差捲動背景：多層山脈、雲霧、前景剪影
# - 程序化美術：自動生成水墨質感素材，無需外部圖檔
# - 視覺強化：漸層天空、地面紋理、光暈特效
# - 手勢控制來自 gestix_mediapipe.SharedState / camera_thread

import pygame, random, time, math
from collections import deque
from threading import Thread
from typing import Optional, Tuple, List

from gestix_mediapipe import SharedState, Config, camera_thread

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
        # 視覺色彩升級
        COLOR_SKY_TOP=(10, 15, 25),      # 天頂：深邃黑藍
        COLOR_SKY_BOT=(30, 40, 60),      # 地平線：墨藍
        COLOR_GROUND=(20, 20, 25),       # 地面主色
        COLOR_TEXT=(230, 230, 230),
        COLOR_BULLET=(255, 160, 60),
        # 大招（護盾）持續時間 & 收集能量
        ULTI_DURATION=5.0,
        COIN_ENERGY_GAIN=10,
        # 槍枝 & 子彈設定
        MAX_BULLETS=3,
        GUN_SPAWN_TIME=20.0,
        # 生成物距離安全閾值
        SAFE_H_DIST=110,
        SAFE_V_DIST=80,
        SAFE_EUCL=150,
        # 手勢 mapping -> 動作
        GESTURE_MAPPING={
            "Fist": "START_GAME",
            "Open": "JUMP",
            "Point1": "PAUSE_TOGGLE",  # 比 1 暫停 / 繼續
            "Gun": "SHOOT",
            "ThumbUp": "RESTART",
            "Victory": "JUMP",         # Victory 當作加強版跳
            "OK": "NONE",
            "DualOpen": "NONE",
        },
    )
    for k, v in defaults.items():
        if not hasattr(Config, k):
            setattr(Config, k, v)

_ensure_config_defaults()

# ------------------ ASSET GENERATORS (程序化素材) ------------------
def create_gradient_surface(w, h, c1, c2):
    """建立垂直漸層背景"""
    surf = pygame.Surface((w, h))
    for y in range(h):
        r = c1[0] + (c2[0] - c1[0]) * y // h
        g = c1[1] + (c2[1] - c1[1]) * y // h
        b = c1[2] + (c2[2] - c1[2]) * y // h
        pygame.draw.line(surf, (r, g, b), (0, y), (w, y))
    return surf

def create_ink_mountain(w, h, color):
    """建立帶有水墨邊緣感的山脈 Surface"""
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    peak_x = random.randint(int(w * 0.3), int(w * 0.7))
    pygame.draw.polygon(surf, color, [(0, h), (w, h), (peak_x, 0)])
    return surf

def create_soft_cloud(radius, color):
    """建立柔邊雲朵"""
    surf = pygame.Surface((radius * 3, radius * 2), pygame.SRCALPHA)
    pygame.draw.circle(surf, (*color, 180), (radius, radius), radius)
    pygame.draw.circle(surf, (*color, 180), (int(radius * 1.8), int(radius * 0.8)), int(radius * 0.8))
    pygame.draw.circle(surf, (*color, 180), (int(radius * 1.5), int(radius * 1.1)), int(radius * 0.7))
    return surf

# ------------------ VISUAL LAYERS (視差系統) ------------------
class ParallaxLayer:
    def __init__(self, scroll_factor, screen_w, item_generator, initial_count=3):
        self.factor = scroll_factor
        self.screen_w = screen_w
        self.items = []  # {'surf', 'x', 'y'}
        self.generator = item_generator

        for _ in range(initial_count):
            self.add_item(x_start=random.randint(0, screen_w))

    def add_item(self, x_start=None):
        if x_start is None:
            x_start = self.screen_w + random.randint(50, 200)
        item_data = self.generator()
        self.items.append(
            {
                "surf": item_data["surf"],
                "x": float(x_start),
                "y": float(item_data["y"]),
            }
        )

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
        surf.blit(
            s,
            (int(self.x - self.radius), int(self.y - self.radius)),
            special_flags=pygame.BLEND_ALPHA_SDL2,
        )

def spawn_coin_sparkles(particles: List[Particle], x, y):
    for _ in range(5):
        ang = random.uniform(0, 2 * math.pi)
        spd = random.uniform(1.5, 3.0)
        particles.append(
            Particle(
                x,
                y,
                math.cos(ang) * spd,
                math.sin(ang) * spd,
                life=0.55,
                color=(255, 192, 203),
                radius=4,
                shape="petal",
            )
        )
    for _ in range(6):
        ang = random.uniform(0, 2 * math.pi)
        spd = random.uniform(2.0, 3.6)
        particles.append(
            Particle(
                x,
                y,
                math.cos(ang) * spd,
                math.sin(ang) * spd,
                life=0.45,
                color=(255, 255, 150),
                radius=3,
            )
        )

def spawn_landing_dust(particles: List[Particle], x, y):
    for _ in range(8):
        vx = random.uniform(-2.4, 2.4)
        vy = random.uniform(-1.6, -0.3)
        particles.append(
            Particle(
                x + random.uniform(-10, 10),
                y,
                vx,
                vy,
                life=0.5,
                color=(120, 105, 95),
                radius=3,
            )
        )

def spawn_bullet_smoke(particles: List[Particle], x, y):
    for _ in range(8):
        ang = random.uniform(0, 2 * math.pi)
        spd = random.uniform(1.0, 2.4)
        particles.append(
            Particle(
                x,
                y,
                math.cos(ang) * spd,
                math.sin(ang) * spd,
                life=0.5,
                color=(200, 200, 200),
                radius=4,
            )
        )

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
        self.has_gun = False
        self.bullets_left = 0
        self.gun_expire_ts = 0.0
        self.prev_rect = self.rect.copy()
        self.trail = deque(maxlen=6)

    def _push_trail(self):
        self.trail.append((self.rect.copy(), time.time()))

    def draw_ninja(self, surf: pygame.Surface):
        now = time.time()
        for r, t0 in self.trail:
            age = now - t0
            if age > 0.25:
                continue
            alpha = max(0, 100 - int(age * 400))
            ghost = pygame.Surface((r.width, r.height), pygame.SRCALPHA)
            pygame.draw.rect(ghost, (50, 60, 80, alpha), (0, 0, r.width, r.height), border_radius=6)
            surf.blit(ghost, r.topleft)

        x, y, w, h = self.rect
        # shadow
        sh = pygame.Surface((50, 10), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 100), (0, 0, 50, 10))
        surf.blit(sh, (self.rect.centerx - 25, self.rect.bottom - 6))

        # scarf
        t = time.time()
        flutter = int(5 * math.sin(t * 12))
        pygame.draw.polygon(
            surf,
            (220, 40, 40),
            [(x + 10, y + 18), (x - 18, y + 14 + flutter), (x - 4, y + 24 + flutter)],
        )

        # body
        pygame.draw.rect(surf, (20, 20, 25), (x + 14, y + 6, 28, 22), border_radius=4)    # head
        pygame.draw.rect(surf, (220, 220, 230), (x + 23, y + 12, 10, 4))                 # eyes
        pygame.draw.rect(surf, (30, 30, 40), (x + 8, y + 28, 42, 44), border_radius=5)   # torso
        pygame.draw.rect(surf, (60, 20, 20), (x + 8, y + 68, 42, 6))                     # belt
        leg_col = (25, 25, 30)
        offset = 2 if self.anim_index == 1 else 0
        pygame.draw.rect(surf, leg_col, (x + 10, y + 74 + offset, 16, 38), border_radius=3)
        pygame.draw.rect(surf, leg_col, (x + 32, y + 74 - offset, 16, 38), border_radius=3)

    def update(self, dt_ms, ground_y, state, particles: List[Particle]):
        self.prev_rect = self.rect.copy()
        if state != "PLAYING":
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
            if not self.on_ground:
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

        if self.has_gun and time.time() > self.gun_expire_ts:
            self.has_gun = False
            self.bullets_left = 0

    def jump(self):
        if self.on_ground:
            self.vel_y = Config.JUMP_VELOCITY
            self.horizontal_boost = 5.8
            self.on_ground = False
        elif self.air_jumps_left > 0:
            self.vel_y = Config.JUMP_VELOCITY
            self.horizontal_boost = 5.0
            self.air_jumps_left -= 1

    def give_gun(self):
        self.has_gun = True
        self.bullets_left = Config.MAX_BULLETS
        self.gun_expire_ts = time.time() + 18.0

    def shoot(self, bullets, all_sprites):
        if self.has_gun and self.bullets_left > 0:
            b = Bullet(self.rect.right + 8, self.rect.centery)
            bullets.add(b)
            all_sprites.add(b)
            self.bullets_left -= 1
            if self.bullets_left <= 0:
                self.has_gun = False

    def land_on(self, top_y):
        self.rect.bottom = top_y
        self.vel_y = 0.0
        self.on_ground = True
        self.air_jumps_left = 1
        self.horizontal_boost = max(self.horizontal_boost * 0.6, 0.0)

class Bullet(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.rect = pygame.Rect(x, y, 14, 8)
        self.speed = Config.BULLET_SPEED

    def update(self, _):
        self.rect.x += self.speed
        if self.rect.left > Config.SCREEN_W + 40:
            self.kill()

    def draw(self, surf):
        pygame.draw.ellipse(surf, Config.COLOR_BULLET, self.rect)
        tail = pygame.Surface((24, 8), pygame.SRCALPHA)
        pygame.draw.ellipse(tail, (*Config.COLOR_BULLET[:3], 100), (0, 0, 24, 8))
        surf.blit(tail, (self.rect.centerx - 20, self.rect.y))

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

class GunPickup(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.rect = pygame.Rect(0, 0, 36, 16)
        self.rect.center = (x, y)
        self.speed = Config.SCROLL_SPEED

    def update(self, _):
        self.rect.x -= self.speed
        if self.rect.right < -40:
            self.kill()

    def draw(self, surf):
        x, y, w, h = self.rect
        pygame.draw.rect(surf, (100, 100, 120), (x, y, w, h), border_radius=4)
        pygame.draw.line(surf, (200, 150, 50), (x + 5, y + h // 2), (x + w - 5, y + h // 2), 2)

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
class GameEngine:
    def __init__(self, shared: SharedState):
        pygame.init()
        self.screen = pygame.display.set_mode((Config.SCREEN_W, Config.SCREEN_H))
        pygame.display.set_caption("GestiX Runner — Ninja Ink (Visual Upgrade)")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 24)
        self.big_font = pygame.font.SysFont("arial", 52, bold=True)
        self.shared = shared
        self.ground_y = Config.SCREEN_H - Config.GROUND_H

        # 背景漸層
        self.bg_gradient = create_gradient_surface(
            Config.SCREEN_W, Config.SCREEN_H, Config.COLOR_SKY_TOP, Config.COLOR_SKY_BOT
        )

        self._init_parallax_layers()

        self.all_sprites = pygame.sprite.Group()
        self.coins = pygame.sprite.Group()
        self.guns = pygame.sprite.Group()
        self.obstacles = pygame.sprite.Group()
        self.bullets = pygame.sprite.Group()
        self.particles: List[Particle] = []

        self.reset_game()

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
        self.guns.empty()
        self.obstacles.empty()
        self.bullets.empty()
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
        self._last_gun_drop = time.time()
        self.game_state = "START"
        self.silhouettes = [
            Silhouette("torii", 600, self.ground_y, Config.SCROLL_SPEED * 0.8)
        ]

    def difficulty(self):
        return min(3.0, (time.time() - self.start_time) / 28.0)

    def poll_gesture_action(self):
        return Config.GESTURE_MAPPING.get(self.shared.get_gesture(), "NONE")

    def _entities(self):
        return list(self.obstacles) + list(self.coins) + list(self.guns)

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
        self.obstacles.add(o)
        self.all_sprites.add(o)

        if random.random() < 0.2:
            kind = random.choice(["pagoda", "torii"])
            self.silhouettes.append(
                Silhouette(kind, Config.SCREEN_W + 160, self.ground_y, Config.SCROLL_SPEED * 0.8)
            )

    def spawn_coin_if_needed(self):
        now = time.time()
        if now < self._coin_cd_until:
            return
        self._coin_cd_until = now + random.uniform(0.95, 1.5)
        y_ground = self.ground_y - 26
        y_air = self.ground_y - 160
        x, y = self._safe_xy(y_ground, y_air)
        c = Coin(x, y)
        self.coins.add(c)
        self.all_sprites.add(c)

    def spawn_gun_if_needed(self):
        now = time.time()
        if now - self._last_gun_drop < Config.GUN_SPAWN_TIME:
            return
        self._last_gun_drop = now
        y_air = self.ground_y - (200 + random.randint(20, 60))
        x, _ = self._safe_xy(self.ground_y - 10, y_air)
        g = GunPickup(x, y_air)
        self.guns.add(g)
        self.all_sprites.add(g)

    def _update_scoring(self):
        if time.time() - self._last_score_t >= 1.0:
            self.score += 20
            self._last_score_t = time.time()

    def _update_shield(self):
        if not self.shield_on and self.energy >= 100:
            self.shield_on = True
            self.shield_until = time.time() + Config.ULTI_DURATION
        if self.shield_on and time.time() > self.shield_until:
            self.shield_on = False
            self.energy = 0

    @staticmethod
    def _intersection_area(a, b):
        if not a.colliderect(b):
            return 0
        x1 = max(a.left, b.left)
        y1 = max(a.top, b.top)
        x2 = min(a.right, b.right)
        y2 = min(a.bottom, b.bottom)
        return max(0, x2 - x1) * max(0, y2 - y1)

    def _handle_collisions(self):
        for c in pygame.sprite.spritecollide(self.player, self.coins, dokill=True):
            self.score += 20
            self.energy = min(100, self.energy + Config.COIN_ENERGY_GAIN)
            spawn_coin_sparkles(self.particles, c.rect.centerx, c.rect.centery)

        if pygame.sprite.spritecollide(self.player, self.guns, dokill=True):
            self.player.give_gun()

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
                    self.game_state = "GAME_OVER"
                    return

    def update(self, dt):
        if self.game_state != "PLAYING":
            return
        self._update_scoring()
        self.spawn_obstacle_if_needed()
        self.spawn_coin_if_needed()
        self.spawn_gun_if_needed()

        self.layer_far.update(Config.SCROLL_SPEED)
        self.layer_mid.update(Config.SCROLL_SPEED)

        for s in list(self.all_sprites):
            if isinstance(s, Player):
                s.update(dt, self.ground_y, self.game_state, self.particles)
            else:
                s.update(dt)

        alive = []
        for p in self.particles:
            if p.update(dt / 1000.0):
                alive.append(p)
        self.particles = alive

        self._update_shield()
        self._handle_collisions()

    def _draw_background(self):
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

        pygame.draw.rect(
            self.screen,
            Config.COLOR_GROUND,
            (0, self.ground_y, Config.SCREEN_W, Config.GROUND_H),
        )
        scroll_x = (time.time() * Config.SCROLL_SPEED * 20) % 60
        for i in range(0, Config.SCREEN_W + 60, 60):
            x = i - scroll_x
            pygame.draw.line(
                self.screen, (30, 35, 45), (x, self.ground_y), (x - 20, Config.SCREEN_H), 2
            )

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
        pygame.draw.rect(
            self.screen,
            (100, 200, 255),
            (BX + 2, frame_y + 2, max(0, fill_w - 2), BAR_H - 3),
        )

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
        pygame.draw.circle(
            halo, (100, 200, 255, alpha), (radius + 5, radius + 5), radius, 3
        )
        self.screen.blit(
            halo,
            (px - radius - 5, py - radius - 5),
            special_flags=pygame.BLEND_ADD,
        )

    def draw(self):
        self._draw_background()
        for o in self.obstacles:
            o.draw(self.screen)
        for c in self.coins:
            c.draw(self.screen)
        for g in self.guns:
            g.draw(self.screen)
        for b in self.bullets:
            b.draw(self.screen)
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
            t = self.big_font.render("PAUSED", True, (255, 255, 255))
            self.screen.blit(t, t.get_rect(center=(Config.SCREEN_W / 2, Config.SCREEN_H / 2)))
        elif self.game_state == "GAME_OVER":
            t1 = self.big_font.render(f"GAME OVER: {int(self.score)}", True, (255, 100, 100))
            t2 = self.big_font.render("ThumbUp to RESTART", True, (220, 220, 220))
            self.screen.blit(t1, t1.get_rect(center=(Config.SCREEN_W / 2, Config.SCREEN_H / 2 - 24)))
            self.screen.blit(t2, t2.get_rect(center=(Config.SCREEN_W / 2, Config.SCREEN_H / 2 + 32)))

        pygame.display.flip()

    def run(self):
        while self.shared.is_running():
            dt = self.clock.tick(Config.GAME_FPS)
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.shared.set_running(False)

            action = self.poll_gesture_action()

            if self.game_state == "START":
                if action == "START_GAME":
                    self.game_state = "PLAYING"
                    self.start_time = time.time()
                    self._last_score_t = time.time()
            elif self.game_state == "PLAYING":
                if action == "PAUSE_TOGGLE":
                    self.game_state = "PAUSED"
                elif action == "JUMP":
                    self.player.jump()
                elif action == "SHOOT":
                    self.player.shoot(self.bullets, self.all_sprites)
            elif self.game_state == "PAUSED":
                if action == "PAUSE_TOGGLE":
                    self.game_state = "PLAYING"
            elif self.game_state == "GAME_OVER":
                if action == "RESTART":
                    self.reset_game()

            self.update(dt)
            self.draw()

        pygame.quit()

if __name__ == "__main__":
    shared = SharedState()
    t = Thread(target=camera_thread, args=(shared,), daemon=True)
    t.start()
    GameEngine(shared).run()
    t.join()
