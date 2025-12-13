# boss_room2.py — Hell Arena Boss (2000 score)
# 強化版 Boss 房：地獄風格、節奏攻擊、紅線預警、合理傷害

import random, time, math
from typing import List
import pygame
from gestix_mediapipe2 import Config
from boss_room import (
    Particle,
    KunaiPickup,
    HealPack,
    HomingKunai,
)

KUNAI_W, KUNAI_H = 36, 12


# =========================
# Hell Boss
# =========================
class HellBoss(pygame.sprite.Sprite):
    def __init__(self, x, ground_y):
        super().__init__()
        self.ground_y = ground_y
        self.rect = pygame.Rect(x, ground_y - 320, 180, 180)

        self.hp_max = 220
        self.hp = self.hp_max

        self._float_t = 0.0
        self._attack_cd = 1.2
        self._warn_lines = []   # [(y, expire_ts)]

    def update(self, dt_ms):
        dt = dt_ms / 1000.0
        self._float_t += dt
        self.rect.y = int(self.ground_y - 320 + 24 * math.sin(self._float_t * 1.8))
        self._attack_cd = max(0.0, self._attack_cd - dt)

    def ready(self):
        return self._attack_cd <= 0.0

    # ---------- 攻擊 1：橫向斬擊 ----------
    def slash(self):
        self._attack_cd = random.uniform(1.6, 2.2)
        y = self.ground_y - random.choice([90, 140, 190])
        self._warn_lines.append((y, time.time() + 0.7))
        return y

    def get_active_slashes(self):
        now = time.time()
        hits = []
        self._warn_lines = [(y, t) for (y, t) in self._warn_lines if t > now]
        for (y, t) in self._warn_lines:
            if t - now < 0.15:
                hits.append(y)
        return hits

    def draw(self, surf):
        x, y, w, h = self.rect
        body = pygame.Surface((w, h), pygame.SRCALPHA)

        # 外殼
        pygame.draw.ellipse(body, (40, 20, 20, 230), (0, 0, w, h))
        pygame.draw.ellipse(body, (120, 40, 40, 90), (12, 18, w - 24, h - 36), 4)

        # 核心
        core_r = 14 + int(4 * math.sin(time.time() * 6))
        pygame.draw.circle(body, (255, 80, 80), (w // 2, h // 2), core_r)

        # 眼
        pygame.draw.circle(body, (255, 140, 140), (int(w * 0.35), int(h * 0.4)), 6)
        pygame.draw.circle(body, (255, 140, 140), (int(w * 0.65), int(h * 0.4)), 6)

        surf.blit(body, (x, y))


# =========================
# Boss Room 2
# =========================
class BossRoom2:
    def __init__(self, player, shared_state, bullets_group):
        self.player = player
        self.shared = shared_state
        self.ground_y = Config.SCREEN_H - Config.GROUND_H

        self.boss = HellBoss(Config.SCREEN_W - 240, self.ground_y)

        self.bullets = bullets_group
        self.kunai_pickups = pygame.sprite.Group()
        self.heal_packs = pygame.sprite.Group()
        self.particles: List[Particle] = []

        self._next_kunai_drop = time.time() + random.uniform(1.2, 2.5)
        self._next_heal_drop = time.time() + float(getattr(Config, "HEAL_PACK_INTERVAL", 6.0))

        self._convert_bullets_to_homing()

    # ---------- 核心共用邏輯 ----------
    def _convert_bullets_to_homing(self):
        for b in list(self.bullets):
            if not isinstance(b, HomingKunai) and hasattr(b, "rect"):
                hk = HomingKunai(b.rect.centerx, b.rect.centery, self.boss)
                b.kill()
                self.bullets.add(hk)

    def is_boss_dead(self):
        return self.boss.hp <= 0

    # ---------- 掉落 ----------
    def _spawn_kunai_if_needed(self):
        if time.time() >= self._next_kunai_drop:
            self._next_kunai_drop = time.time() + random.uniform(1.2, 2.5)
            y = self.ground_y - random.randint(120, 200)
            self.kunai_pickups.add(KunaiPickup(Config.SCREEN_W + 40, y))

    def _spawn_heal_if_needed(self):
        if time.time() >= self._next_heal_drop:
            self._next_heal_drop = time.time() + float(getattr(Config, "HEAL_PACK_INTERVAL", 6.0))
            self.heal_packs.add(HealPack(Config.SCREEN_W + 40, self.ground_y - 60))

    # ---------- 碰撞 ----------
    def _update_collisions(self):
        # 撿苦無 → 追蹤苦無
        for _ in pygame.sprite.spritecollide(self.player, self.kunai_pickups, True):
            self.bullets.add(HomingKunai(
                self.player.rect.right + 8,
                self.player.rect.centery,
                self.boss
            ))

        # 撿血
        for _ in pygame.sprite.spritecollide(self.player, self.heal_packs, True):
            self.player.hp = min(self.player.max_hp, self.player.hp + 20)

        # 苦無打 Boss
        hits = pygame.sprite.spritecollide(self.boss, self.bullets, True)
        if hits:
            self.boss.hp -= 18 * len(hits)

        # 橫斬擊命中（低傷害）
        for y in self.boss.get_active_slashes():
            if abs(self.player.rect.centery - y) < 26:
                if not self.player.shield_on:
                    self.player.hp -= 10

    # ---------- 更新 ----------
    def update(self, dt_ms):
        self.boss.update(dt_ms)

        if self.boss.ready():
            self.boss.slash()

        self._convert_bullets_to_homing()

        for b in list(self.bullets):
            b.update(dt_ms)

        self._spawn_kunai_if_needed()
        for k in self.kunai_pickups:
            k.update(dt_ms)

        self._spawn_heal_if_needed()
        for h in self.heal_packs:
            h.update(dt_ms)

        self._update_collisions()

    # ---------- 繪製 ----------
    def draw(self, surf):
        surf.fill((30, 10, 10))

        # 地獄地板
        pygame.draw.rect(
            surf, (50, 20, 20),
            (0, self.ground_y, Config.SCREEN_W, Config.GROUND_H + 20)
        )

        # 紅線預警
        for (y, t) in self.boss._warn_lines:
            alpha = int(120 + 80 * math.sin(time.time() * 12))
            line = pygame.Surface((Config.SCREEN_W, 4), pygame.SRCALPHA)
            line.fill((255, 60, 60, alpha))
            surf.blit(line, (0, y))

        # 掉落物
        for k in self.kunai_pickups:
            k.draw(surf)
        for h in self.heal_packs:
            h.draw(surf)

        # Boss
        self.boss.draw(surf)

        # Boss HP
        BAR_W = 420
        ratio = max(0.0, self.boss.hp / self.boss.hp_max)
        pygame.draw.rect(surf, (80, 30, 30), ((Config.SCREEN_W - BAR_W)//2, 18, BAR_W, 18))
        pygame.draw.rect(
            surf, (220, 80, 80),
            ((Config.SCREEN_W - BAR_W)//2, 18, int(BAR_W * ratio), 18)
        )
