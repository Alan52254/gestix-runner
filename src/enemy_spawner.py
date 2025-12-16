# enemy_spawner.py — generic spawn helpers (optional utility)

import random
import pygame
from typing import List, Tuple
from gestix_mediapipe2 import Config


def rect_center(r: pygame.Rect) -> Tuple[int, int]:
    return r.centerx, r.centery


def _dist_ok(ax, ay, bx, by):
    dx, dy = abs(ax - bx), abs(ay - by)
    if dx < Config.SAFE_H_DIST: return False
    if dy < Config.SAFE_V_DIST: return False
    if (dx*dx+dy*dy)**0.5 < Config.SAFE_EUCL: return False
    return True


def safe_xy(entities: List[pygame.sprite.Sprite], y_ground: int, y_air: int) -> Tuple[int, int]:
    for _ in range(24):
        x = Config.SCREEN_W + random.randint(40, 140)
        y = random.choice([y_ground, y_air])
        ok = True
        for e in entities:
            ex, ey = rect_center(e.rect)
            if not _dist_ok(x, y, ex, ey):
                ok = False
                break
        if ok:
            return x, y
    return Config.SCREEN_W + 220, y_ground


def keep_apart(new_rect: pygame.Rect, others: List[pygame.Rect], pad: int) -> bool:
    a = new_rect.inflate(pad, pad)
    for o in others:
        if a.colliderect(o.inflate(pad, pad)):
            return False
    return True


def push_right_until_safe(r: pygame.Rect, others: List[pygame.Rect], pad: int, limit_x: int) -> pygame.Rect:
    tries, step = 0, 32
    while not keep_apart(r, others, pad) and tries < 24 and r.x < limit_x:
        r.x += step
        tries += 1
    return r
