import pygame
import random
import time
import math
from typing import List
from gestix_mediapipe2 import Config

# ------------------ CONSTANTS ------------------
PLAYER_MAX_HP = 200
BOSS_MAX_HP = 1000

# 玩家苦無命中 Boss
SOUL_KUNAI_DMG = 18
SOUL_SEAL_TIME = 0.35

# 補給
HEAL_AMOUNT = 25
ENERGY_ORB_GAIN = 20

# Boss 房內「苦無拾取物」
KUNAI_PICKUP_GAIN = 1
KUNAI_PICKUP_INTERVAL = 2.5
KUNAI_PICKUP_SPEED = 4.2

# Boss 攻擊參數
REAPER_SHOT_DMG = 20
REAPER_SHOT_SPEED = 7.0
REAPER_SHOT_SIZE = 18

# Kunai auto-homing
HOMING_SPEED = 9.0

GROUND_Y = Config.SCREEN_H - Config.GROUND_H

# ------------------ PARTICLE ------------------
class Particle:
    def __init__(self, x, y, vx, vy, life, color, radius):
        self.x, self.y = float(x), float(y)
        self.vx, self.vy = float(vx), float(vy)
        self.life = float(life)
        self.t = 0.0
        self.color = color
        self.radius = int(radius)

    def update(self, dt):
        self.t += dt
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.03
        return self.t < self.life

    def draw(self, surf):
        a = max(0, int(255 * (1 - self.t / self.life)))
        s = pygame.Surface((self.radius * 2 + 2, self.radius * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*self.color, a), (self.radius + 1, self.radius + 1), self.radius)
        surf.blit(s, (int(self.x - self.radius), int(self.y - self.radius)), special_flags=pygame.BLEND_ADD)


# ------------------ BOSS ------------------
class Reaper(pygame.sprite.Sprite):
    def __init__(self):
        super().__init__()
        self.rect = pygame.Rect(Config.SCREEN_W - 260, GROUND_Y - 260, 180, 180)
        self.hp_max = BOSS_MAX_HP
        self.hp = self.hp_max
        self.float_t = 0.0
        self.attack_cd = 1.5
        self.sealed_until = 0.0
        self.phase = 1

    def sealed(self):
        return time.time() < self.sealed_until

    def ready(self):
        return self.attack_cd <= 0.0 and not self.sealed()

    def reset_cd(self, duration=1.5):
        self.attack_cd = duration

    def update(self, dt_ms):
        if self.sealed():
            return
        dt = dt_ms / 1000.0
        self.float_t += dt
        self.rect.y = int(GROUND_Y - 300 + math.sin(self.float_t * 2.2) * 22)
        self.attack_cd -= dt

    def draw(self, surf):
        x, y, w, h = self.rect
        body = pygame.Surface((w, h), pygame.SRCALPHA)

        # Body Color
        base_col = (20, 20, 25, 240)
        eye_col = (120, 200, 255)

        if self.phase == 2:
            base_col = (15, 10, 20, 255)
            eye_col = (255, 60, 120)

        pygame.draw.ellipse(body, base_col, (20, 0, w - 40, h - 20))
        pygame.draw.circle(body, eye_col, (w // 2 - 22, h // 2 - 10), 6)
        pygame.draw.circle(body, eye_col, (w // 2 + 22, h // 2 - 10), 6)

        # Glow
        glow = pygame.Surface((w + 100, h + 100), pygame.SRCALPHA)
        if self.phase == 2:
            pygame.draw.circle(glow, (180, 40, 100, 80), ((w + 100) // 2, (h + 100) // 2), 130)
        else:
            pygame.draw.circle(glow, (60, 100, 180, 70), ((w + 100) // 2, (h + 100) // 2), 120)
        
        surf.blit(glow, (x - 50, y - 50), special_flags=pygame.BLEND_ADD)
        
        if self.sealed():
            pygame.draw.ellipse(body, (150, 200, 255, 60), (10, 10, w - 20, h - 20), 3)

        surf.blit(body, (x, y))


# ------------------ PROJECTILES ------------------
class SoulOrb(pygame.sprite.Sprite):
    def __init__(self, x, y, target):
        super().__init__()
        self.x, self.y = float(x), float(y)
        self.target = target
        self.speed = 9.0
        self.rect = pygame.Rect(int(x), int(y), 26, 26)

    def update(self, dt_ms):
        if not self.target:
            self.kill()
            return
        tx, ty = self.target.rect.center
        dx, dy = tx - self.x, ty - self.y
        dist = max(1.0, math.hypot(dx, dy))
        self.x += self.speed * dx / dist
        self.y += self.speed * dy / dist
        self.rect.center = (int(self.x), int(self.y))

    def draw(self, surf):
        cx, cy = self.rect.center
        pygame.draw.circle(surf, (200, 230, 255), (cx, cy), 7)
        pygame.draw.circle(surf, (100, 150, 255), (cx, cy), 13, 2)

class ReaperShot(pygame.sprite.Sprite):
    def __init__(self, x, y, vx, vy, is_ground_wave=False, is_bouncing=False):
        super().__init__()
        self.x, self.y = float(x), float(y)
        self.vx, self.vy = float(vx), float(vy)
        
        # 尺寸設定
        w = REAPER_SHOT_SIZE
        h = REAPER_SHOT_SIZE
        if is_ground_wave:
            w, h = 90, 24
        elif is_bouncing:
            w, h = 24, 24 # 彈跳彈稍微大一點
        
        self.rect = pygame.Rect(int(x), int(y), w, h)
        self.is_ground_wave = is_ground_wave
        self.is_bouncing = is_bouncing

    def update(self, dt_ms):
        # 彈跳邏輯
        if self.is_bouncing:
            # 碰到地板反彈
            if self.rect.bottom >= GROUND_Y and self.vy > 0:
                self.vy = -abs(self.vy)
            # 碰到天花板(或一定高度)反彈
            elif self.rect.top <= 0 and self.vy < 0:
                self.vy = abs(self.vy)

        self.x += self.vx
        self.y += self.vy
        self.rect.center = (int(self.x), int(self.y))
        
        if (self.rect.right < -50 or self.rect.left > Config.SCREEN_W + 50 or
                self.rect.bottom < -50 or self.rect.top > Config.SCREEN_H + 50):
            self.kill()

    def draw(self, surf):
        cx, cy = self.rect.center
        if self.is_ground_wave:
            pygame.draw.ellipse(surf, (180, 40, 40), self.rect)
            pygame.draw.ellipse(surf, (255, 120, 120), self.rect, 3)
        elif self.is_bouncing:
            # 彈跳彈：帶有旋轉感的視覺
            pygame.draw.circle(surf, (100, 255, 100), (cx, cy), 10)
            pygame.draw.circle(surf, (200, 255, 200), (cx, cy), 13, 2)
        else:
            pygame.draw.circle(surf, (150, 180, 255), (cx, cy), 6)
            pygame.draw.circle(surf, (80, 100, 220), (cx, cy), 9, 2)


# ------------------ PICKUPS (Gestix Style with Glow) ------------------
class HealPack(pygame.sprite.Sprite):
    def __init__(self):
        super().__init__()
        self.rect = pygame.Rect(Config.SCREEN_W + 40, GROUND_Y - 60, 26, 18)

    def update(self, dt_ms):
        self.rect.x -= 3
        if self.rect.right < -40: self.kill()

    def draw(self, surf):
        # 經典綠底白十字
        pygame.draw.rect(surf, (40, 180, 60), self.rect, border_radius=4)
        pygame.draw.rect(surf, (255, 255, 255), (self.rect.centerx - 3, self.rect.top + 3, 6, self.rect.height - 6))
        pygame.draw.rect(surf, (255, 255, 255), (self.rect.left + 4, self.rect.centery - 3, self.rect.width - 8, 6))

class EnergyOrb(pygame.sprite.Sprite):
    def __init__(self):
        super().__init__()
        self.rect = pygame.Rect(Config.SCREEN_W + 40, GROUND_Y - 140, 24, 24)

    def update(self, dt_ms):
        self.rect.x -= 4
        if self.rect.right < -40: self.kill()

    def draw(self, surf):
        cx, cy = self.rect.center
        pygame.draw.circle(surf, (100, 210, 255), (cx, cy), 9)
        pygame.draw.circle(surf, (180, 240, 255), (cx, cy), 13, 1)

class KunaiPickup(pygame.sprite.Sprite):
    """
    使用 gestix_runner2.py 中的高級樣式 (發光 + 閃爍 + 劍身)
    """
    def __init__(self, x, y):
        super().__init__()
        self.rect = pygame.Rect(0, 0, 26, 10)
        self.rect.center = (x, y)
        self.vx = -KUNAI_PICKUP_SPEED

    def update(self, dt_ms):
        self.rect.x += int(self.vx)
        if self.rect.right < -60: self.kill()

    def draw(self, surf):
        x, y, w, h = self.rect
        t = time.time()
        
        # 1. Glow (發光)
        glow = pygame.Surface((w + 56, h + 56), pygame.SRCALPHA)
        cx, cy = (w + 56) // 2, (h + 56) // 2
        for r, alpha in [(30, 65), (22, 95), (16, 120), (10, 150)]:
            pygame.draw.circle(glow, (255, 230, 160, alpha), (cx, cy), r)
        surf.blit(glow, (x - 28, y - 28), special_flags=pygame.BLEND_ADD)

        # 2. Twinkle (閃爍星芒)
        twinkle = pygame.Surface((70, 70), pygame.SRCALPHA)
        pygame.draw.line(twinkle, (255, 245, 220, 110), (35, 0), (35, 70), 2)
        pygame.draw.line(twinkle, (255, 245, 220, 110), (0, 35), (70, 35), 2)
        ang = (t * 120) % 360
        twinkle = pygame.transform.rotozoom(twinkle, ang, 1.0)
        rect = twinkle.get_rect(center=(x + w // 2, y + h // 2))
        surf.blit(twinkle, rect.topleft, special_flags=pygame.BLEND_ADD)

        # 3. Blade (本體)
        blade = pygame.Surface((w + 8, h + 6), pygame.SRCALPHA)
        pygame.draw.polygon(blade, (220, 220, 230), [(0, h // 2 + 3), (14, 0), (14, h + 6)])
        pygame.draw.rect(blade, (60, 60, 80), (14, 2, w - 6, h + 2), border_radius=2)
        surf.blit(blade, (x - 4, y - 3))


# ------------------ FINAL BOSS ROOM ------------------
class BossRoomFinal:
    def __init__(self, player, shared, bullets):
        self.player = player
        self.shared = shared
        self.bullets = bullets 

        # 狀態初始化
        self.player.max_hp = PLAYER_MAX_HP
        self.player.hp = PLAYER_MAX_HP
        self.player.energy = 0
        if not hasattr(self.player, "kunai_stack"): self.player.kunai_stack = 0
        if not hasattr(self.player, "kunai_max"): self.player.kunai_max = getattr(Config, "KUNAI_MAX_STACK", 10)

        self.boss = Reaper()
        self.enemy_shots = pygame.sprite.Group()
        self.heals = pygame.sprite.Group()
        self.energy_orbs = pygame.sprite.Group()
        self.kunai_pickups = pygame.sprite.Group()
        self.particles: List[Particle] = []
                # ------------------ Fan Shot (方案 C：時間錯開) ------------------
        self._fan_queue = []        # 等待發射的扇形子彈角度
        self._fan_next_time = 0.0   # 下一顆允許射出的時間


        # 生成計時
        self.next_heal = time.time() + 5.0
        self.next_energy = time.time() + 3.0
        self.next_kunai_pickup = time.time() + 1.0

        # 大招狀態
        self.black_judgement_used = False
        self.freeze_until = 0.0
        self.ulti_active_until = 0.0
        
        # 瞬移視覺
        self.teleport_fx_until = 0.0
        self.teleport_start = None
        self.teleport_end = None

        # 自動射擊 & Boss 階段
        self._auto_fire_next = time.time() + 0.3
        self.phase2 = False
        self.phase2_fx_until = 0.0

        # ★ Boss 攻擊模式
        self.attack_mode = 0
        self.mode_switch_time = time.time() + 5.0

    def is_boss_dead(self) -> bool:
        self.boss.hp = max(0, self.boss.hp)
        return self.boss.hp <= 0

    # ------------------ ULTIMATE: SUPER SAIYAN ------------------
    def cast_final_ulti(self):
        if self.black_judgement_used: return
        if getattr(self.player, "energy", 0) < 100: return

        self.player.energy = 0
        now = time.time()
        self.black_judgement_used = True
        
        # 4秒定身
        self.freeze_until = now + 4.0
        self.ulti_active_until = now + 4.2

        self.teleport_start = self.player.rect.center
        target_x = self.boss.rect.left - 60
        target_y = self.boss.rect.centery
        self.teleport_end = (target_x, target_y)
        self.teleport_fx_until = now + 0.5

        self.player.rect.center = (target_x, target_y)

        damage = int(self.boss.hp * 0.5)
        self.boss.hp -= damage

        for _ in range(8):
            self.bullets.add(SoulOrb(self.player.rect.centerx, self.player.rect.centery, self.boss))

    # ------------------ BOSS ATTACK LOGIC ------------------
    def _handle_boss_attack(self):
        now = time.time()
        
        # 模式循環
        if now > self.mode_switch_time:
            self.attack_mode = (self.attack_mode + 1) % 4
            self.mode_switch_time = now + 4.5
        
        cx, cy = self.boss.rect.center
        px, py = self.player.rect.center

        # Mode 0: 單發精準射擊
        if self.attack_mode == 0:
            ang = math.atan2(py - cy, px - cx)
            vx = math.cos(ang) * REAPER_SHOT_SPEED
            vy = math.sin(ang) * REAPER_SHOT_SPEED
            self.enemy_shots.add(ReaperShot(cx, cy, vx, vy))
            self.boss.reset_cd(1.0 if self.phase2 else 1.4)

        # Mode 1: 扇形擴散
        elif self.attack_mode == 1:
            base_ang = math.atan2(py - cy, px - cx)
            spread = 0.35

            self._fan_queue = [
            base_ang - spread,
            base_ang,
            base_ang + spread
            ]
            self._fan_next_time = time.time()
            self.boss.reset_cd(1.6 if self.phase2 else 2.0)


        # Mode 2: 地面波 (巨大化)
        elif self.attack_mode == 2:
            vx = -REAPER_SHOT_SPEED * 1.1
            self.enemy_shots.add(ReaperShot(cx, GROUND_Y - 35, vx, 0, is_ground_wave=True))
            self.boss.reset_cd(1.5 if self.phase2 else 2.0)
            
        # ★ Mode 3: 彈跳鐮刀 (Bouncing Scythe) - 新增模式
        # 產生 2 發會上下彈跳的子彈，玩家需要看準時機從縫隙鑽過
        elif self.attack_mode == 3:
            # 第一發：往下射，反彈向上
            self.enemy_shots.add(ReaperShot(
                cx, cy, 
                -REAPER_SHOT_SPEED * 0.9, # 橫向速度
                REAPER_SHOT_SPEED * 0.8,  # 初始向下
                is_bouncing=True
            ))
            # 第二發：往上射，反彈向下 (Phase 2 才出這發，增加難度)
            if self.phase2:
                self.enemy_shots.add(ReaperShot(
                    cx, cy, 
                    -REAPER_SHOT_SPEED * 0.9, 
                    -REAPER_SHOT_SPEED * 0.8, # 初始向上
                    is_bouncing=True
                ))
            
            self.boss.reset_cd(1.6 if self.phase2 else 2.0)

    # ------------------ UPDATE ------------------
    def update(self, dt_ms):
        now = time.time()
        dt = dt_ms / 1000.0

        # Phase 2 檢查
        if not self.phase2 and self.boss.hp < self.boss.hp_max * 0.5:
            self.phase2 = True
            self.boss.phase = 2
            self.phase2_fx_until = now + 1.2
            global REAPER_SHOT_DMG, REAPER_SHOT_SPEED
            REAPER_SHOT_DMG = int(REAPER_SHOT_DMG * 1.3)
            REAPER_SHOT_SPEED *= 1.15

        # Boss 行為
        if now >= self.freeze_until:
            self.boss.update(dt_ms)
            if self.boss.ready():
                self._handle_boss_attack()
        if self._fan_queue and time.time() >= self._fan_next_time:
            ang = self._fan_queue.pop(0)
            cx, cy = self.boss.rect.center
            vx = math.cos(ang) * (REAPER_SHOT_SPEED * 0.9)
            vy = math.sin(ang) * (REAPER_SHOT_SPEED * 0.9)
            self.enemy_shots.add(ReaperShot(cx, cy, vx, vy))

            # 控制「頻率」就在這裡
            self._fan_next_time = time.time() + (0.08 if self.phase2 else 0.32)

        # 生成補給
        if now >= self.next_heal:
            self.next_heal = now + 8.0
            self.heals.add(HealPack())
        if now >= self.next_energy:
            self.next_energy = now + random.uniform(2.5, 4.0)
            self.energy_orbs.add(EnergyOrb())
        if now >= self.next_kunai_pickup:
            self.next_kunai_pickup = now + KUNAI_PICKUP_INTERVAL
            y = random.randint(GROUND_Y - 200, GROUND_Y - 80)
            self.kunai_pickups.add(KunaiPickup(Config.SCREEN_W + 40, y))

        # 碰撞判定
        for s in list(self.enemy_shots):
            s.update(dt_ms)
            if s.rect.colliderect(self.player.rect):
                if not getattr(self.player, "shield_on", False):
                    self.player.hp -= REAPER_SHOT_DMG
                s.kill()

        # 吸收物品
        for h in pygame.sprite.spritecollide(self.player, self.heals, True):
            self.player.hp = min(PLAYER_MAX_HP, self.player.hp + HEAL_AMOUNT)
        for e in pygame.sprite.spritecollide(self.player, self.energy_orbs, True):
            self.player.energy = min(100, self.player.energy + ENERGY_ORB_GAIN)
        for k in pygame.sprite.spritecollide(self.player, self.kunai_pickups, True):
            self.player.kunai_stack = min(self.player.kunai_max, self.player.kunai_stack + KUNAI_PICKUP_GAIN)

        # 其它更新
        for g in [self.heals, self.energy_orbs, self.kunai_pickups]:
            g.update(dt_ms)

        # ★ 自動射擊苦無
        if now >= self._auto_fire_next and self.player.kunai_stack > 0:
            if hasattr(self.player, "shoot_kunai"):
                self.player.shoot_kunai(self.bullets, None)
            self._auto_fire_next = now + (0.2 if self.phase2 else 0.25)

        # 子彈追蹤 Boss
        for b in list(self.bullets):
            if hasattr(b, "target"):
                b.update(dt_ms) # SoulOrb
            else:
                tx, ty = self.boss.rect.center
                dx, dy = tx - b.rect.centerx, ty - b.rect.centery
                dist = max(1.0, math.hypot(dx, dy))
                b.rect.x += int(HOMING_SPEED * dx / dist)
                b.rect.y += int(HOMING_SPEED * dy / dist)
            
            if b.rect.colliderect(self.boss.rect):
                self.boss.hp -= SOUL_KUNAI_DMG
                self.boss.sealed_until = time.time() + SOUL_SEAL_TIME
                b.kill()

        # 粒子特效
        if random.random() < 0.4:
            self.particles.append(Particle(
                self.player.rect.centerx, self.player.rect.bottom,
                random.uniform(-1,1), -2, 0.5, (200,100,50), 4
            ))
        self.particles = [p for p in self.particles if p.update(dt)]

    # ------------------ DRAW ------------------
    def draw(self, surf):
        surf.fill((15, 12, 20))
        pygame.draw.rect(surf, (8, 5, 10), (0, GROUND_Y, Config.SCREEN_W, Config.GROUND_H + 20))

        # 1. Boss
        self.boss.draw(surf)

        now = time.time()

        # 2. Phase 2 爆氣光環
        if now < self.phase2_fx_until:
            cx, cy = self.boss.rect.center
            pygame.draw.circle(surf, (255, 100, 150), (cx, cy), 160, 5)

        # 3. 大招視覺
        if now < self.ulti_active_until:
            if now < self.teleport_fx_until and self.teleport_start and self.teleport_end:
                pygame.draw.line(surf, (100, 255, 255), self.teleport_start, self.teleport_end, 3)
            
            px, py = self.player.rect.center
            aura = pygame.Surface((200, 200), pygame.SRCALPHA)
            pygame.draw.circle(aura, (255, 255, 200, 80), (100, 100), 70)
            pygame.draw.circle(aura, (255, 255, 255, 150), (100, 100), 50, 2)
            surf.blit(aura, (px-100, py-100), special_flags=pygame.BLEND_ADD)

        # 4. 畫物件
        for g in [self.enemy_shots, self.heals, self.energy_orbs, self.kunai_pickups]:
            for s in g: s.draw(surf)
        for p in self.particles: p.draw(surf)

        # 5. 血條
        bar_w = 400
        bx = (Config.SCREEN_W - bar_w) // 2
        pygame.draw.rect(surf, (50, 50, 60), (bx, 20, bar_w, 20), 2)
        ratio = max(0, self.boss.hp / self.boss.hp_max)
        col = (255, 80, 80) if not self.phase2 else (255, 50, 120)
        pygame.draw.rect(surf, col, (bx+2, 22, int((bar_w-4)*ratio), 16))

        if self.phase2:
            font = pygame.font.SysFont("arial", 20, bold=True)
            txt = font.render("PHASE 2 - RAGE", True, (255, 100, 100))
            surf.blit(txt, (bx + bar_w + 10, 18))