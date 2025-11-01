# gestix_runner.py
# GestiX Runner — Ninja Ink (no images; fully drawn)
# - 960x540 小尺寸、流暢水墨風背景（紅月、群山、雲、剪影）
# - 忍者角色（黑衣＋紅圍巾），跑步殘影、落地煙霧、護盾光暈
# - 靈魂球(coin)、空中苦無袋(gun)；矩形墨柱/浮空木樁障礙
# - 槍只在空中；所有物件保持水平/垂直/斜向安全距離
# - 可踩障礙頂；側/底實質重疊才死亡（較不敏感）
# - 分數、能量(Chakra)與 5 秒護盾；手勢同前（Fist/Open/Point1/Gun/ThumbUp）

import pygame, random, time, math
from collections import deque
from threading import Thread
from typing import Optional, Tuple, List

from gestix_mediapipe import SharedState, Config, camera_thread


# ------------------ CONFIG DEFAULTS ------------------
def _ensure_config_defaults():
    defaults = dict(
        SCREEN_W=960, SCREEN_H=540, GAME_FPS=60, SCROLL_SPEED=5,
        GRAVITY=1.04, JUMP_VELOCITY=-17,
        GROUND_H=56, BULLET_SPEED=16,
        COLOR_SKY=(12, 18, 28),      # 深靛夜空
        COLOR_GROUND=(24, 36, 46),   # 墨色地面
        COLOR_TEXT=(230, 230, 230),
        COLOR_BULLET=(250, 170, 80),
        ULTI_DURATION=5.0, COIN_ENERGY_GAIN=10,
        MAX_BULLETS=3, GUN_SPAWN_TIME=20.0,
        SAFE_H_DIST=110, SAFE_V_DIST=80, SAFE_EUCL=150,
        GESTURE_MAPPING={
            "Fist": "START_GAME",
            "Open": "JUMP",
            "Point1": "PAUSE_TOGGLE",
            "Gun": "SHOOT",
            "ThumbUp": "RESTART",
            "Victory": "JUMP",
            "OK": "NONE",
            "DualOpen": "NONE",
        },
    )
    for k, v in defaults.items():
        if not hasattr(Config, k):
            setattr(Config, k, v)
_ensure_config_defaults()


# ------------------ HELPERS ------------------
def rect_center(rect: pygame.Rect) -> Tuple[int, int]:
    return rect.centerx, rect.centery

def dist_ok(ax, ay, bx, by):
    dx, dy = abs(ax - bx), abs(ay - by)
    if dx < Config.SAFE_H_DIST: return False
    if dy < Config.SAFE_V_DIST: return False
    if (dx*dx + dy*dy) ** 0.5 < Config.SAFE_EUCL: return False
    return True


# ------------------ PARTICLES ------------------
class Particle:
    def __init__(self, x, y, vx, vy, life, color, radius, fade=True, shape="circle"):
        self.x, self.y = float(x), float(y)
        self.vx, self.vy = float(vx), float(vy)
        self.life = float(life)
        self.t = 0.0
        self.color = color
        self.radius = radius
        self.fade = fade
        self.shape = shape  # "circle" or "petal"

    def update(self, dt):
        self.t += dt
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.05  # 微重力
        return self.t < self.life

    def draw(self, surf):
        alpha = 255
        if self.fade:
            alpha = max(0, int(255 * (1 - self.t / self.life)))
        col = (*self.color[:3], alpha)
        s = pygame.Surface((self.radius*2+2, self.radius*2+2), pygame.SRCALPHA)
        if self.shape == "petal":
            pygame.draw.ellipse(s, col, (1, 1, self.radius*2, int(self.radius*1.2)))
        else:
            pygame.draw.circle(s, col, (self.radius+1, self.radius+1), self.radius)
        surf.blit(s, (int(self.x - self.radius), int(self.y - self.radius)))


def spawn_coin_sparkles(particles: List[Particle], x, y):
    # 櫻花花瓣＋微光
    for _ in range(5):
        ang = random.uniform(0, 2*math.pi); spd = random.uniform(1.5, 3.0)
        particles.append(Particle(x, y, math.cos(ang)*spd, math.sin(ang)*spd,
                                  life=0.55, color=(255, 192, 203), radius=4, shape="petal"))
    for _ in range(6):
        ang = random.uniform(0, 2*math.pi); spd = random.uniform(2.0, 3.6)
        particles.append(Particle(x, y, math.cos(ang)*spd, math.sin(ang)*spd,
                                  life=0.45, color=(255, 240, 120), radius=3))

def spawn_landing_dust(particles: List[Particle], x, y):
    for _ in range(8):
        vx = random.uniform(-2.4, 2.4); vy = random.uniform(-1.6, -0.3)
        particles.append(Particle(x + random.uniform(-10,10), y, vx, vy, life=0.5,
                                  color=(120,105,95), radius=3))

def spawn_bullet_smoke(particles: List[Particle], x, y):
    for _ in range(8):
        ang = random.uniform(0, 2*math.pi); spd = random.uniform(1.0, 2.4)
        particles.append(Particle(x, y, math.cos(ang)*spd, math.sin(ang)*spd,
                                  life=0.5, color=(150,150,150), radius=4))


# ------------------ 背景（墨色層） ------------------
class CloudInk:
    def __init__(self, x, y, scale=1.0):
        self.x, self.y, self.scale = float(x), float(y), scale
        self.speed = 0.45 * scale
    def update(self):
        self.x -= self.speed
        return self.x > -160
    def draw(self, surf):
        x, y, s = int(self.x), int(self.y), self.scale
        col = (220,220,230)
        pygame.draw.circle(surf, col, (x, y), int(22*s))
        pygame.draw.circle(surf, col, (x+22, y+6), int(18*s))
        pygame.draw.circle(surf, col, (x-20, y+10), int(16*s))

class InkHill:
    def __init__(self, x, base_y, w, h, color, speed):
        self.x, self.base_y, self.w, self.h = float(x), base_y, w, h
        self.color, self.speed = color, speed
    def update(self):
        self.x -= self.speed
        return self.x + self.w > -50
    def draw(self, surf):
        pygame.draw.polygon(
            surf, self.color,
            [(self.x, self.base_y), (self.x + self.w/2, self.base_y - self.h), (self.x + self.w, self.base_y)]
        )

class Silhouette:
    # pagoda / torii 剪影
    def __init__(self, kind, x, ground_y, speed):
        self.kind = kind
        self.x = float(x); self.ground_y = ground_y; self.speed = speed
    def update(self):
        self.x -= self.speed
        return self.x > -200
    def draw(self, surf):
        x = int(self.x); y = self.ground_y
        col = (30, 30, 40)
        if self.kind == "pagoda":
            pygame.draw.rect(surf, col, (x, y-70, 80, 10))
            pygame.draw.rect(surf, col, (x+8, y-120, 64, 8))
            pygame.draw.rect(surf, col, (x+22, y-146, 36, 6))
            pygame.draw.rect(surf, col, (x+38, y-170, 8, 24))
        else:  # torii
            pygame.draw.rect(surf, col, (x, y-64, 8, 64))
            pygame.draw.rect(surf, col, (x+56, y-64, 8, 64))
            pygame.draw.rect(surf, col, (x-8, y-68, 88, 8))
            pygame.draw.rect(surf, col, (x-4, y-80, 80, 6))


# ------------------ PLAYER（忍者） ------------------
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

        # 殘影（跑步拖尾）
        self.trail = deque(maxlen=6)

    def _push_trail(self):
        self.trail.append((self.rect.copy(), time.time()))

    def draw_ninja(self, surf: pygame.Surface):
        # Trail
        now = time.time()
        for i, (r, t0) in enumerate(self.trail):
            age = now - t0
            if age > 0.25: continue
            alpha = max(0, 120 - int(age*480))
            ghost = pygame.Surface((r.width, r.height), pygame.SRCALPHA)
            pygame.draw.rect(ghost, (80, 80, 100, alpha), (0, 0, r.width, r.height), border_radius=6)
            surf.blit(ghost, r.topleft)

        x, y, w, h = self.rect
        # 地面陰影
        sh = pygame.Surface((50, 10), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0,0,0,80), (0,0,50,10))
        surf.blit(sh, (self.rect.centerx-25, self.rect.bottom-8))

        # 紅圍巾（飄動）
        t = time.time(); flutter = int(5*math.sin(t*10))
        pygame.draw.polygon(surf, (200,40,50), [(x+10, y+18), (x-12, y+16+flutter), (x-2, y+22+flutter)])

        # 頭部（面罩＋眼縫）
        pygame.draw.rect(surf, (30,30,36), (x+14, y+6, 28, 22), border_radius=3)
        pygame.draw.rect(surf, (210,210,220), (x+23, y+12, 10, 6))

        # 身體護甲
        pygame.draw.rect(surf, (40,45,60), (x+8, y+28, 42, 44), border_radius=4)
        pygame.draw.rect(surf, (60,65,85), (x+8, y+28, 42, 10), border_radius=3)

        # 手臂
        pygame.draw.rect(surf, (40,45,60), (x-8, y+30, 12, 12), border_radius=3)
        pygame.draw.rect(surf, (40,45,60), (x+w-6, y+30, 12, 12), border_radius=3)

        # 腰甲＋腿
        pygame.draw.rect(surf, (70,75,95), (x+6, y+74, 46, 10), border_radius=3)
        leg_col = (50,55,75) if self.anim_index == 0 else (42,48,68)
        pygame.draw.rect(surf, leg_col, (x+10, y+86, 16, 28), border_radius=3)
        pygame.draw.rect(surf, leg_col, (x+32, y+86, 16, 28), border_radius=3)

        # 鞋
        pygame.draw.rect(surf, (95,65,45), (x+8, y+112, 18, 8), border_radius=2)
        pygame.draw.rect(surf, (95,65,45), (x+32, y+112, 18, 8), border_radius=2)

    def update(self, dt_ms, ground_y, state, particles: List[Particle]):
        self.prev_rect = self.rect.copy()
        if state != "PLAYING":
            return

        # 物理
        if not self.on_ground:
            self.vel_y += Config.GRAVITY
            self.rect.y += int(self.vel_y)
            if self.horizontal_boost > 0:
                self.rect.x += int(self.horizontal_boost)
                self.rect.x = min(self.rect.x, self.base_x + self.max_forward)
                self.horizontal_boost *= 0.94

        # 落地
        if self.rect.bottom >= ground_y:
            self.rect.bottom = ground_y
            if not self.on_ground:
                spawn_landing_dust(particles, self.rect.centerx, ground_y - 3)
                self.air_jumps_left = 1
            self.vel_y = 0.0
            self.on_ground = True
        else:
            self.on_ground = False

        # 回位
        if self.on_ground and self.rect.x > self.base_x:
            self.rect.x -= min(3, self.rect.x - self.base_x)

        # 動畫與殘影
        self.anim_timer += dt_ms / 1000.0
        if self.anim_timer >= self.anim_speed:
            self.anim_timer = 0.0
            self.anim_index = (self.anim_index + 1) % 2
            self._push_trail()

        # 槍時效
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
            bullets.add(b); all_sprites.add(b)
            self.bullets_left -= 1
            if self.bullets_left <= 0:
                self.has_gun = False

    def land_on(self, top_y):
        self.rect.bottom = top_y
        self.vel_y = 0.0
        self.on_ground = True
        self.air_jumps_left = 1
        self.horizontal_boost = max(self.horizontal_boost * 0.6, 0.0)


# ------------------ 其他精靈 ------------------
class Bullet(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.rect = pygame.Rect(x, y, 10, 10)
        self.speed = Config.BULLET_SPEED
    def update(self, _):
        self.rect.x += self.speed
        if self.rect.left > Config.SCREEN_W + 40:
            self.kill()
    def draw(self, surf):
        # 子彈與簡單拖尾
        pygame.draw.circle(surf, Config.COLOR_BULLET, self.rect.center, 5)
        tail = pygame.Surface((18, 6), pygame.SRCALPHA)
        pygame.draw.ellipse(tail, (250,170,80,120), (0,0,18,6))
        surf.blit(tail, (self.rect.centerx-20, self.rect.centery-3))

class Coin(pygame.sprite.Sprite):
    # 靈魂球
    def __init__(self, x, y):
        super().__init__()
        self.rect = pygame.Rect(0, 0, 28, 28)
        self.rect.center = (x, y)
        self.speed = Config.SCROLL_SPEED
        self.anim = 0
    def update(self, _):
        self.rect.x -= self.speed
        if self.rect.right < -40:
            self.kill()
        self.anim = (self.anim + 1) % 24
    def draw(self, surf):
        cx, cy = self.rect.center
        glow = (170, 220, 255)
        pygame.draw.circle(surf, (240, 240, 255), (cx, cy), 13, 2)
        pygame.draw.circle(surf, glow, (cx, cy), 9)

class GunPickup(pygame.sprite.Sprite):
    # 空中苦無袋
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
        pygame.draw.rect(surf, (90, 90, 105), (x, y, w, h), border_radius=3)
        pygame.draw.rect(surf, (60, 60, 70), (x, y, w, h), 2, border_radius=3)
        pygame.draw.rect(surf, (230, 140, 60), (x + w - 7, y + 4, 5, 8))

class Obstacle(pygame.sprite.Sprite):
    # 墨柱 / 浮空木樁
    def __init__(self, x, ground_y, air, scale):
        super().__init__()
        h = random.randint(60, 200)
        w = random.randint(50, 90)
        yb = ground_y - (220 + random.randint(0, 80)) if air else ground_y
        self.rect = pygame.Rect(x, yb - h, w, h)
        self.speed = int(Config.SCROLL_SPEED * (1.0 + 0.22 * scale))
    def update(self, _):
        self.rect.x -= self.speed
        if self.rect.right < -60:
            self.kill()
    def draw(self, surf):
        x, y, w, h = self.rect
        pygame.draw.rect(surf, (45,45,55), (x, y, w, h), border_radius=4)
        pygame.draw.rect(surf, (70,70,90), (x, y, w, 8), border_radius=3)


# ------------------ GAME ENGINE ------------------
class GameEngine:
    def __init__(self, shared: SharedState):
        pygame.init()
        self.screen = pygame.display.set_mode((Config.SCREEN_W, Config.SCREEN_H))
        pygame.display.set_caption("GestiX Runner — Ninja Ink (960x540)")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 24)
        self.big_font = pygame.font.SysFont("arial", 52, bold=True)
        self.shared = shared
        self.ground_y = Config.SCREEN_H - Config.GROUND_H

        # 背景層
        self.clouds: List[CloudInk] = []
        self.hills: List[InkHill] = []
        self.silhouettes: List[Silhouette] = []

        # Sprites
        self.all_sprites = pygame.sprite.Group()
        self.coins = pygame.sprite.Group()
        self.guns = pygame.sprite.Group()
        self.obstacles = pygame.sprite.Group()
        self.bullets = pygame.sprite.Group()

        # 粒子
        self.particles: List[Particle] = []

        self.reset_game()

    def reset_game(self):
        self.all_sprites.empty(); self.coins.empty(); self.guns.empty()
        self.obstacles.empty(); self.bullets.empty(); self.particles.clear()
        self.player = Player(140, self.ground_y)
        self.all_sprites.add(self.player)
        self.score = 0; self.energy = 0
        self.shield_on = False; self.shield_until = 0.0
        self.start_time = time.time(); self._last_score_t = time.time()
        self._obs_cd_until = 0.0; self._coin_cd_until = 0.0
        self._last_gun_drop = time.time()
        self.game_state = "START"

        # 背景初始
        self.clouds = [CloudInk(random.randint(0, Config.SCREEN_W), random.randint(60, 160), random.uniform(0.8,1.2)) for _ in range(3)]
        self.hills = [
            InkHill(180, self.ground_y, 240, 110, (22,28,40), 0.45),
            InkHill(520, self.ground_y, 200, 90, (26,32,45), 0.6),
            InkHill(840, self.ground_y, 320, 140, (18,24,36), 0.35),
        ]
        self.silhouettes = [
            Silhouette("pagoda", 360, self.ground_y, 0.8),
            Silhouette("torii", 760, self.ground_y, 0.8),
        ]

    def difficulty(self):
        return min(3.0, (time.time() - self.start_time) / 28.0)

    def poll_gesture_action(self):
        return Config.GESTURE_MAPPING.get(self.shared.get_gesture(), "NONE")

    # ---- spawn helpers ----
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
                    ok = False; break
            if ok: return x, y
        return Config.SCREEN_W + 220, y_ground

    def _rightmost_obstacle_x(self) -> Optional[int]:
        return max((o.rect.right for o in self.obstacles), default=None)

    # ---- spawners ----
    def spawn_obstacle_if_needed(self):
        now = time.time()
        if now < self._obs_cd_until: return
        d = self.difficulty()
        min_gap = 380 - int(28 * d)
        rightmost = self._rightmost_obstacle_x()
        if rightmost and rightmost > Config.SCREEN_W - min_gap: return
        self._obs_cd_until = now + max(1.0, 1.45 - 0.14 * d)

        air_prob = 0.32 + 0.1 * d
        is_air = random.random() < air_prob

        x, _ = self._safe_xy(self.ground_y - 10, self.ground_y - 220)
        o = Obstacle(x, self.ground_y, is_air, d)
        self.obstacles.add(o); self.all_sprites.add(o)

        if random.random() < 0.16:
            kind = random.choice(["pagoda", "torii"])
            self.silhouettes.append(Silhouette(kind, Config.SCREEN_W + 160, self.ground_y, 0.8))

    def spawn_coin_if_needed(self):
        now = time.time()
        if now < self._coin_cd_until: return
        self._coin_cd_until = now + random.uniform(0.95, 1.5)
        y_ground = self.ground_y - 26
        y_air = self.ground_y - 160
        x, y = self._safe_xy(y_ground, y_air)
        c = Coin(x, y)
        self.coins.add(c); self.all_sprites.add(c)

    def spawn_gun_if_needed(self):
        now = time.time()
        if now - self._last_gun_drop < Config.GUN_SPAWN_TIME: return
        self._last_gun_drop = now
        y_air = self.ground_y - (200 + random.randint(20, 60))
        x, _ = self._safe_xy(self.ground_y - 10, y_air)
        g = GunPickup(x, y_air)
        self.guns.add(g); self.all_sprites.add(g)

    # ---- score & shield ----
    def _update_scoring(self):
        if time.time() - self._last_score_t >= 1.0:
            self.score += 20; self._last_score_t = time.time()

    def _update_shield(self):
        if not self.shield_on and self.energy >= 100:
            self.shield_on = True
            self.shield_until = time.time() + Config.ULTI_DURATION
        if self.shield_on and time.time() > self.shield_until:
            self.shield_on = False; self.energy = 0

    # ---- collisions ----
    @staticmethod
    def _intersection_area(a: pygame.Rect, b: pygame.Rect) -> int:
        if not a.colliderect(b): return 0
        x1 = max(a.left, b.left); y1 = max(a.top, b.top)
        x2 = min(a.right, b.right); y2 = min(a.bottom, b.bottom)
        return max(0, x2 - x1) * max(0, y2 - y1)

    def _handle_collisions(self):
        # Coins
        for c in pygame.sprite.spritecollide(self.player, self.coins, dokill=True):
            self.score += 20
            self.energy = min(100, self.energy + Config.COIN_ENERGY_GAIN)
            spawn_coin_sparkles(self.particles, c.rect.centerx, c.rect.centery)

        # Gun
        if pygame.sprite.spritecollide(self.player, self.guns, dokill=True):
            self.player.give_gun()

        # Bullet vs obstacle
        hits = pygame.sprite.groupcollide(self.bullets, self.obstacles, True, True)
        for _ in hits.values():
            spawn_bullet_smoke(self.particles, self.player.rect.centerx + 100, self.player.rect.centery - 30)
            self.score += 50

        # Player vs obstacle：頂踩 / 實質重疊才死
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

            inter_area = self._intersection_area(pbox, obox)
            min_area = min(pbox.width * pbox.height, obox.width * obox.height)
            lethal = inter_area >= 0.35 * min_area

            if lethal:
                if self.shield_on:
                    ob.kill(); self.score += 50
                else:
                    self.game_state = "GAME_OVER"; return
            # 擦邊不判死

    # ---- update ----
    def update(self, dt):
        if self.game_state != "PLAYING": return
        self._update_scoring()
        self.spawn_obstacle_if_needed(); self.spawn_coin_if_needed(); self.spawn_gun_if_needed()

        for s in list(self.all_sprites):
            if isinstance(s, Player): s.update(dt, self.ground_y, self.game_state, self.particles)
            else: s.update(dt)

        # 粒子
        alive = []
        for p in self.particles:
            if p.update(dt/1000.0): alive.append(p)
        self.particles = alive

        self._update_shield()
        self._handle_collisions()

    # ---- draw ----
    def _draw_background(self):
        self.screen.fill(Config.COLOR_SKY)
        # 紅月
        pygame.draw.circle(self.screen, (200, 55, 55), (int(Config.SCREEN_W*0.78), 90), 40)
        pygame.draw.circle(self.screen, (170, 40, 40), (int(Config.SCREEN_W*0.78)+6, 88), 40, 3)

        # 山
        for h in list(self.hills):
            if not h.update():
                self.hills.remove(h)
                self.hills.append(InkHill(Config.SCREEN_W+random.randint(100,240), self.ground_y,
                                          random.randint(200,320), random.randint(90,150),
                                          (18+random.randint(0,10), 24+random.randint(0,10), 36+random.randint(0,10)),
                                          0.35+random.random()*0.3))
            h.draw(self.screen)
        # 剪影
        for s in list(self.silhouettes):
            if not s.update(): self.silhouettes.remove(s)
            else: s.draw(self.screen)
        # 雲
        for cl in list(self.clouds):
            if not cl.update():
                self.clouds.remove(cl)
                self.clouds.append(CloudInk(Config.SCREEN_W+140, random.randint(60,160), random.uniform(0.8,1.2)))
            cl.draw(self.screen)

        # 地面
        pygame.draw.rect(self.screen, Config.COLOR_GROUND,
                         (0, self.ground_y, Config.SCREEN_W, Config.GROUND_H))
        for i in range(3):
            y = self.ground_y + i*16
            pygame.draw.line(self.screen, (36, 54, 66), (0,y), (Config.SCREEN_W,y), 3)

    def _draw_hud(self):
        # score
        t = self.font.render(f"Score: {int(self.score)}", True, Config.COLOR_TEXT)
        self.screen.blit(t, (Config.SCREEN_W - t.get_width() - 14, 10))
        # chakra
        BAR_W, BAR_H = 200, 18
        BX, BY = 14, 12
        lbl = self.font.render("Chakra", True, (200, 200, 220))
        self.screen.blit(lbl, (BX, BY - 6))
        frame_y = BY + lbl.get_height() - 10
        pygame.draw.rect(self.screen, (80,80,92), (BX, frame_y, BAR_W, BAR_H), 2)
        fill_w = int(BAR_W * (self.energy/100.0))
        r = int(160*(1-self.energy/100.0)); g = int(210*(self.energy/100.0)); b = 220
        pygame.draw.rect(self.screen, (r,g,b), (BX+2, frame_y+2, max(0,fill_w-2), BAR_H-3))

    def _draw_shield(self):
        if not self.shield_on: return
        px, py = self.player.rect.center
        radius = 72
        t = time.time()
        alpha = 85 + int(45 * (0.5 + 0.5*math.sin(t*7)))
        halo = pygame.Surface((radius*2+10, radius*2+10), pygame.SRCALPHA)
        pygame.draw.circle(halo, (240,240,100,alpha), (radius+5, radius+5), radius, 5)
        self.screen.blit(halo, (px-radius-5, py-radius-5))

    def draw(self):
        self._draw_background()

        # Sprites
        for o in self.obstacles: o.draw(self.screen)
        for c in self.coins: c.draw(self.screen)
        for g in self.guns: g.draw(self.screen)
        for b in self.bullets: b.draw(self.screen)
        self.player.draw_ninja(self.screen)

        # Particles
        for p in self.particles: p.draw(self.screen)

        self._draw_shield()
        self._draw_hud()

        # States
        if self.game_state == "START":
            t = self.big_font.render("Fist to START", True, (240,240,240))
            self.screen.blit(t, t.get_rect(center=(Config.SCREEN_W/2, Config.SCREEN_H/2)))
        elif self.game_state == "PAUSED":
            t = self.big_font.render("Paused (Point1 to resume)", True, (240,240,240))
            self.screen.blit(t, t.get_rect(center=(Config.SCREEN_W/2, Config.SCREEN_H/2)))
        elif self.game_state == "GAME_OVER":
            t1 = self.big_font.render(f"GAME OVER! Score: {int(self.score)}", True, (240,240,240))
            t2 = self.big_font.render("ThumbUp to RESTART", True, (240,240,240))
            self.screen.blit(t1, t1.get_rect(center=(Config.SCREEN_W/2, Config.SCREEN_H/2 - 24)))
            self.screen.blit(t2, t2.get_rect(center=(Config.SCREEN_W/2, Config.SCREEN_H/2 + 32)))

        pygame.display.flip()

    # ---- main loop ----
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


# ------------------ ENTRY ------------------
if __name__ == "__main__":
    shared = SharedState()
    t = Thread(target=camera_thread, args=(shared,), daemon=True)
    t.start()  # Camera debug window handled by gestix_mediapipe.py
    GameEngine(shared).run()
    t.join()
