# boss_room.py — Boss room with palace, boss(200HP), fireballs, auto-homing kunai on pickup, HUD bar
import random, time, math
from typing import List
import pygame
from gestix_mediapipe2 import Config

# 與外界一致的苦無尺寸
KUNAI_W, KUNAI_H = 36, 12

class Particle:
    def __init__(self, x, y, vx, vy, life, color, radius):
        self.x, self.y = float(x), float(y)
        self.vx, self.vy = float(vx), float(vy)
        self.life = float(life)
        self.t = 0.0
        self.color = color
        self.radius = radius

    def update(self, dt):
        self.t += dt
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.02
        return self.t < self.life

    def draw(self, surf):
        alpha = max(0, int(255 * (1 - self.t / self.life)))
        s = pygame.Surface((self.radius*2+2, self.radius*2+2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*self.color, alpha), (self.radius+1, self.radius+1), self.radius)
        surf.blit(s, (int(self.x-self.radius), int(self.y-self.radius)), special_flags=pygame.BLEND_ADD)

class Boss(pygame.sprite.Sprite):
    def __init__(self, x, ground_y):
        super().__init__()
        self.ground_y = ground_y
        self.rect = pygame.Rect(x, ground_y - 280, 160, 160)
        self.hp_max = 200
        self.hp = self.hp_max
        self._float_t = 0.0
        self._shot_cd = 0.0

    def update(self, dt_ms):
        dt = dt_ms / 1000.0
        self._float_t += dt
        self.rect.y = int(self.ground_y - 300 + 20 * math.sin(self._float_t * 2.0))
        self._shot_cd = max(0.0, self._shot_cd - dt)

    def ready_to_fire(self):
        return self._shot_cd <= 0.0

    def fire(self, player_center):
        # 射擊間隔拉長 0.5 秒（原 0.9~1.6 → 1.4~2.1）
        self._shot_cd = random.uniform(1.4, 2.1)
        px, py = player_center
        sx, sy = self.rect.center
        ang = math.atan2(py - sy, px - sx)
        spd = 7.2
        return Fireball(sx, sy, math.cos(ang)*spd, math.sin(ang)*spd)

    def draw(self, surf):
        x, y, w, h = self.rect
        body = pygame.Surface((w, h), pygame.SRCALPHA)
        # 簡化 BOSS（你要換耿鬼時可在這裡畫）
        pygame.draw.ellipse(body, (20, 20, 28, 230), (0, 0, w, h))
        pygame.draw.circle(body, (220, 60, 60), (int(w*0.35), int(h*0.42)), 8)
        pygame.draw.circle(body, (220, 60, 60), (int(w*0.65), int(h*0.42)), 8)
        surf.blit(body, (x, y))

class Fireball(pygame.sprite.Sprite):
    def __init__(self, x, y, vx, vy):
        super().__init__()
        self.x, self.y = float(x), float(y)
        self.vx, self.vy = float(vx), float(vy)
        self.rect = pygame.Rect(int(self.x)-15, int(self.y)-15, 30, 30)

    def update(self, dt_ms):
        self.x += self.vx
        self.y += self.vy
        self.rect.center = (int(self.x), int(self.y))
        if (self.rect.right < -60 or self.rect.left > Config.SCREEN_W + 60 or
                self.rect.bottom < -60 or self.rect.top > Config.SCREEN_H + 60):
            self.kill()

    def draw(self, surf):
        cx, cy = self.rect.center
        glow_radius = 45 + int(5 * math.sin(time.time() * 20))
        glow_surf = pygame.Surface((glow_radius*2, glow_radius*2), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (255, 100, 50, 40), (glow_radius, glow_radius), glow_radius)
        surf.blit(glow_surf, (cx - glow_radius, cy - glow_radius), special_flags=pygame.BLEND_ADD)
        mid_radius = 28
        mid_surf = pygame.Surface((mid_radius*2, mid_radius*2), pygame.SRCALPHA)
        pygame.draw.circle(mid_surf, (255, 200, 50, 80), (mid_radius, mid_radius), mid_radius)
        surf.blit(mid_surf, (cx - mid_radius, cy - mid_radius), special_flags=pygame.BLEND_ADD)
        pygame.draw.circle(surf, (255, 255, 200), (cx, cy), 12)
        pygame.draw.circle(surf, (255, 255, 255), (cx, cy), 8)

class KunaiPickup(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.rect = pygame.Rect(0, 0, 26, 10)
        self.rect.center = (x, y)
        self.speed = Config.SCROLL_SPEED

    def update(self, dt_ms):
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

class HealPack(pygame.sprite.Sprite):
    """Boss 房專用回血補包：被玩家碰到回 33 HP"""
    def __init__(self, x, y):
        super().__init__()
        self.rect = pygame.Rect(0, 0, 26, 18)
        self.rect.center = (x, y)
        self.speed = 3  # 慢慢從右往左飄

    def update(self, dt_ms):
        self.rect.x -= self.speed
        if self.rect.right < -40:
            self.kill()

    def draw(self, surf):
        x, y, w, h = self.rect
        # 外圈綠色光暈
        glow = pygame.Surface((w + 40, h + 40), pygame.SRCALPHA)
        cx, cy = (w + 40) // 2, (h + 40) // 2
        for r, alpha in [(18, 90), (24, 60)]:
            pygame.draw.circle(glow, (120, 220, 160, alpha), (cx, cy), r)
        surf.blit(glow, (x - 20, y - 20), special_flags=pygame.BLEND_ADD)
        # 中間綠色補包 + 白色十字
        pack = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(pack, (30, 60, 50), (0, 0, w, h), border_radius=4)
        pygame.draw.rect(pack, (200, 255, 230), (w//2 - 2, 3, 4, h - 6))
        pygame.draw.rect(pack, (200, 255, 230), (4, h//2 - 2, w - 8, 4))
        surf.blit(pack, (x, y))

class HomingKunai(pygame.sprite.Sprite):
    def __init__(self, x, y, target_sprite: pygame.sprite.Sprite):
        super().__init__()
        self.x, self.y = float(x), float(y)
        self.speed = 12.0
        self.target = target_sprite
        self.rect = pygame.Rect(int(self.x), int(self.y) - KUNAI_H//2, KUNAI_W, KUNAI_H)

    def update(self, dt_ms):
        if not self.target or not hasattr(self.target, "rect"):
            self.kill(); return
        tx, ty = self.target.rect.center
        dx, dy = tx - self.x, ty - self.y
        dist = max(1e-3, (dx*dx + dy*dy)**0.5)
        vx, vy = self.speed * dx / dist, self.speed * dy / dist
        self.x += vx
        self.y += vy
        self.rect.center = (int(self.x), int(self.y))
        if (self.rect.right < -60 or self.rect.left > Config.SCREEN_W + 60 or
            self.rect.bottom < -60 or self.rect.top > Config.SCREEN_H + 60):
            self.kill()

    def draw(self, surf):
        x, y, w, h = self.rect
        blade = pygame.Surface((w + 12, h + 8), pygame.SRCALPHA)
        pygame.draw.polygon(blade, (210, 210, 220), [(0, h//2+4), (18, 0), (18, h+8)])
        pygame.draw.rect(blade, (70, 70, 90), (18, 2, w - 10, h + 4), border_radius=3)
        surf.blit(blade, (x - 6, y - 4))

class BossRoom:
    def __init__(self, player, shared_state, bullets_group):
        self.player = player
        self.shared = shared_state
        self.ground_y = Config.SCREEN_H - Config.GROUND_H

        self.boss = Boss(Config.SCREEN_W - 220, self.ground_y)
        self.fireballs = pygame.sprite.Group()
        self.kunai_pickups = pygame.sprite.Group()
        self.heal_packs = pygame.sprite.Group()
        # 共用外界 bullets 群組（包含直線苦無與轉換後的追蹤苦無）
        self.bullets = bullets_group
        self.particles: List[Particle] = []

        # 房內苦無掉落間隔（可調整）
        self._next_kunai_drop = time.time() + random.uniform(1.0, 3.0)
        # 房內回血補包掉落間隔（使用 Config.HEAL_PACK_INTERVAL）
        self._next_heal_drop = time.time() + float(getattr(Config, "HEAL_PACK_INTERVAL", 6.0))

        # 進房不清空玩家子彈；將場上直線苦無轉成追蹤苦無
        self._convert_bullets_to_homing()

    # 宮殿背景
    def _draw_palace_bg(self, surf):
        surf.fill((40, 30, 50))
        floor_h = Config.GROUND_H + 20
        floor_y = Config.SCREEN_H - floor_h
        pygame.draw.rect(surf, (20, 15, 30), (0, floor_y, Config.SCREEN_W, floor_h))
        carpet_h = 100
        carpet_y = floor_y + (floor_h - carpet_h) // 2
        pygame.draw.rect(surf, (100, 20, 30), (0, carpet_y, Config.SCREEN_W, carpet_h))
        pygame.draw.line(surf, (200, 180, 50), (0, carpet_y), (Config.SCREEN_W, carpet_y), 3)
        pygame.draw.line(surf, (200, 180, 50), (0, carpet_y+carpet_h), (Config.SCREEN_W, carpet_y+carpet_h), 3)
        pillar_w = 60
        pillar_color = (70, 60, 80)
        highlight = (90, 80, 100)
        for x in range(50, Config.SCREEN_W, 300):
            pygame.draw.rect(surf, pillar_color, (x, 0, pillar_w, floor_y))
            pygame.draw.rect(surf, highlight, (x + 10, 0, 10, floor_y))
            pygame.draw.rect(surf, (50, 40, 60), (x - 10, floor_y - 30, pillar_w + 20, 30))

    # 將現有直線苦無轉追蹤
    def _convert_bullets_to_homing(self):
        for b in list(self.bullets):
            if not isinstance(b, HomingKunai) and hasattr(b, "rect"):
                hk = HomingKunai(b.rect.centerx, b.rect.centery, self.boss)
                b.kill()
                self.bullets.add(hk)

    def is_boss_dead(self) -> bool:
        return self.boss.hp <= 0

    def is_cleared(self) -> bool:
        return self.is_boss_dead()

    def _spawn_kunai_if_needed(self):
        if time.time() >= self._next_kunai_drop:
            self._next_kunai_drop = time.time() + random.uniform(1.0, 3.0)
            y = self.ground_y - (160 + random.randint(-30, 40))
            self.kunai_pickups.add(KunaiPickup(Config.SCREEN_W + 40, y))

    def _spawn_heal_if_needed(self):
        interval = float(getattr(Config, "HEAL_PACK_INTERVAL", 6.0))
        if time.time() >= self._next_heal_drop:
            self._next_heal_drop = time.time() + interval
            y = self.ground_y - 60  # 略高於地面
            x = Config.SCREEN_W + 40
            self.heal_packs.add(HealPack(x, y))

    def _update_collisions(self):
        # 撿到苦無：自動釋放追蹤苦無（不需手勢）
        for _ in pygame.sprite.spritecollide(self.player, self.kunai_pickups, dokill=True):
            hk = HomingKunai(self.player.rect.right + 8, self.player.rect.centery, self.boss)
            self.bullets.add(hk)
            for _i in range(6):
                self.particles.append(Particle(
                    self.player.rect.centerx, self.player.rect.top + 10,
                    random.uniform(-1.5, 1.5), random.uniform(-2.0, -0.2),
                    0.6, (255, 230, 160), 3
                ))

        # 撿到回血補包：+33 HP，最多到 max_hp
        for _ in pygame.sprite.spritecollide(self.player, self.heal_packs, dokill=True):
            max_hp = getattr(self.player, "max_hp", 100)
            self.player.hp = min(max_hp, self.player.hp + 33)
            for _i in range(8):
                self.particles.append(Particle(
                    self.player.rect.centerx,
                    self.player.rect.centery - 20,
                    random.uniform(-1.2, 1.2),
                    random.uniform(-2.0, -0.4),
                    0.7,
                    (120, 220, 160),
                    4
                ))

        # 苦無擊中 BOSS
        hits = pygame.sprite.spritecollide(self.boss, self.bullets, dokill=True)
        if hits:
            self.boss.hp -= 20 * len(hits)

        # 火球打到玩家（護盾免傷）
        for fb in list(self.fireballs):
            if fb.rect.colliderect(self.player.rect.inflate(-6, -6)):
                fb.kill()
                if not getattr(self.player, "shield_on", False):
                    self.player.hp -= 33

        # 下限保護（死亡由外層 runner2 判斷）
        self.player.hp = max(self.player.hp, -9999)

    def update(self, dt_ms):
        self.boss.update(dt_ms)

        if self.boss.ready_to_fire():
            self.fireballs.add(self.boss.fire(self.player.rect.center))

        for fb in list(self.fireballs):
            fb.update(dt_ms)

        # 把房內新丟出的直線苦無持續轉追蹤
        self._convert_bullets_to_homing()

        for b in list(self.bullets):
            b.update(dt_ms)

        self._spawn_kunai_if_needed()
        for k in list(self.kunai_pickups):
            k.update(dt_ms)

        self._spawn_heal_if_needed()
        for h in list(self.heal_packs):
            h.update(dt_ms)

        self.particles = [p for p in self.particles if p.update(dt_ms/1000.0)]
        self._update_collisions()

    def _draw_boss_hp(self, surf):
        BAR_W, BAR_H = 420, 22
        x = (Config.SCREEN_W - BAR_W)//2
        y = 18
        pygame.draw.rect(surf, (60,60,70), (x, y, BAR_W, BAR_H), 2, border_radius=6)
        ratio = max(0.0, min(1.0, self.boss.hp / float(self.boss.hp_max)))
        fill = int((BAR_W-4)*ratio)
        pygame.draw.rect(surf, (220,80,80), (x+2, y+2, fill, BAR_H-4), border_radius=5)
        font = pygame.font.SysFont("arial", 20, bold=True)
        txt = font.render(f"BOSS HP: {max(0, self.boss.hp)}/{self.boss.hp_max}", True, (240,240,240))
        surf.blit(txt, (x + (BAR_W-txt.get_width())//2, y-20))

    def draw(self, surf):
        # 先畫宮殿背景
        self._draw_palace_bg(surf)
        # 房內掉落物、火球、回血補包
        for k in self.kunai_pickups:
            k.draw(surf)
        for h in self.heal_packs:
            h.draw(surf)
        for fb in self.fireballs:
            fb.draw(surf)
        # Boss（玩家與子彈由外層 runner2 統一繪製，確保層級正確）
        self.boss.draw(surf)
        # 粒子與 Boss 血條
        for p in self.particles:
            p.draw(surf)
        self._draw_boss_hp(surf)
