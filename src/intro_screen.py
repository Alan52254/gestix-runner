# intro_screen.py
# -----------------------------
# GestiX Runner — Intro / Tutorial Screen (ENGLISH ONLY)
# - Runs before gestix_runner2.GameEngine
# - Usage:
#     from intro_screen import run_intro
#     run_intro(shared)
# - Controls:
#     ThumbUp : Next page
#     Fist    : Skip all intro and start game
#     Space / → : Next page (keyboard debug)
#     Esc     : Skip intro
# -----------------------------

import pygame
import time

from gestix_mediapipe2 import SharedState, Config


# Ensure minimal config exists (in case runner not loaded yet)
def _ensure_intro_config_defaults():
    defaults = dict(
        SCREEN_W=960,
        SCREEN_H=540,
        GAME_FPS=60,
        COLOR_SKY_TOP=(10, 15, 25),
        COLOR_SKY_BOT=(30, 40, 60),
        COLOR_TEXT=(230, 230, 230),
    )
    for k, v in defaults.items():
        if not hasattr(Config, k):
            setattr(Config, k, v)


_ensure_intro_config_defaults()


def create_gradient_surface(w, h, c1, c2):
    """Simple vertical gradient background"""
    surf = pygame.Surface((w, h))
    for y in range(h):
        r = c1[0] + (c2[0] - c1[0]) * y // h
        g = c1[1] + (c2[1] - c1[1]) * y // h
        b = c1[2] + (c2[2] - c1[2]) * y // h
        pygame.draw.line(surf, (r, g, b), (0, y), (w, y))
    return surf


class IntroScreen:
    def __init__(self, shared: SharedState):
        self.shared = shared

        pygame.init()
        self.screen = pygame.display.set_mode((Config.SCREEN_W, Config.SCREEN_H))
        pygame.display.set_caption("GestiX Runner — Intro / Tutorial")

        self.clock = pygame.time.Clock()
        self.bg = create_gradient_surface(
            Config.SCREEN_W,
            Config.SCREEN_H,
            Config.COLOR_SKY_TOP,
            Config.COLOR_SKY_BOT,
        )

        # Fonts (English safe)
        self.title_font = pygame.font.SysFont("arial", 44, bold=True)
        self.body_font = pygame.font.SysFont("arial", 24)
        self.hint_font = pygame.font.SysFont("arial", 18)

        # Tutorial pages (ENGLISH)
        self.pages = [
            dict(
                title="Story: The Last Ink Ninja",
                lines=[
                    "You are the Ink Ninja, the final guardian of the mountain shrine.",
                    "A dark rift has shattered the barrier, spawning cursed obstacles and fireballs.",
                    "Control your body with hand gestures and survive the endless corridor.",
                    "Enter the palace, defeat the Boss, and restore peace to the night.",
                ],
            ),
            dict(
                title="Gestures: Control with Your Hands",
                lines=[
                    "Fist: Start the game. In intro, skip all pages instantly.",
                    "Open / Victory: Jump and double-jump to dodge obstacles.",
                    "Gun: Throw kunai forward to destroy obstacles.",
                    "ThumbUp: Next page in intro. Restart the game after Game Over.",
                ],
            ),
            dict(
                title="System: Items, Chakra, Ultimate",
                lines=[
                    "Glowing orbs are Chakra Coins: increase score and energy.",
                    "Floating kunai pickups increase your kunai stock.",
                    "Green heal packs appear in the Boss Room and restore HP.",
                    "Chakra at 100: DualOpen activates a temporary shield ultimate.",
                ],
            ),
            dict(
                title="Boss Fight Tips",
                lines=[
                    "When the score reaches the threshold, a portal will appear.",
                    "Approach the portal to enter the Boss Room.",
                    "The Boss fires continuous fireballs: jump and shield wisely.",
                    "Defeat the Boss to fully restore HP and return to the world.",
                ],
            ),
        ]

        self.current_page = 0
        self.last_advance_time = 0.0
        self.last_gesture = None

    # Simple ninja silhouette decoration
    def _draw_ninja_silhouette(self, surf):
        w, h = 70, 120
        x = Config.SCREEN_W // 2 - w // 2 - 220
        y = Config.SCREEN_H - h - 40
        s = pygame.Surface((w, h), pygame.SRCALPHA)

        pygame.draw.rect(s, (20, 22, 30, 230), (10, 20, w - 20, h - 30), border_radius=12)
        pygame.draw.rect(s, (15, 17, 24, 230), (18, 0, w - 36, 30), border_radius=10)
        pygame.draw.rect(s, (220, 220, 240, 230), (22, 10, w - 44, 6))
        pygame.draw.rect(s, (120, 90, 65, 230), (14, h - 18, 20, 16), border_radius=4)
        pygame.draw.rect(s, (120, 90, 65, 230), (w - 34, h - 18, 20, 16), border_radius=4)

        surf.blit(s, (x, y))

    def _draw_page_indicator(self, surf):
        total = len(self.pages)
        r = 7
        gap = 24
        total_w = (total - 1) * gap
        start_x = Config.SCREEN_W // 2 - total_w // 2
        y = Config.SCREEN_H - 60

        for i in range(total):
            cx = start_x + i * gap
            color = (255, 220, 120) if i == self.current_page else (160, 160, 180)
            pygame.draw.circle(surf, color, (cx, y), r)

    def _draw_page(self):
        self.screen.blit(self.bg, (0, 0))

        overlay = pygame.Surface((Config.SCREEN_W, Config.SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 90))
        self.screen.blit(overlay, (0, 0))

        page = self.pages[self.current_page]

        title_surf = self.title_font.render(page["title"], True, (255, 240, 210))
        self.screen.blit(
            title_surf,
            title_surf.get_rect(center=(Config.SCREEN_W / 2, 90)),
        )

        start_y = 170
        line_spacing = 40
        for i, line in enumerate(page["lines"]):
            txt = self.body_font.render(line, True, Config.COLOR_TEXT)
            rect = txt.get_rect(center=(Config.SCREEN_W / 2, start_y + i * line_spacing))
            self.screen.blit(txt, rect)

        self._draw_ninja_silhouette(self.screen)

        hint_txt = self.hint_font.render(
            "ThumbUp: Next   Fist: Skip Intro   Space/→: Next   Esc: Skip",
            True,
            (220, 220, 230),
        )
        self.screen.blit(
            hint_txt,
            hint_txt.get_rect(center=(Config.SCREEN_W / 2, Config.SCREEN_H - 30)),
        )

        self._draw_page_indicator(self.screen)

    def _handle_input(self):
        should_quit = False
        should_skip_all = False
        should_next = False

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                should_quit = True
            elif e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_RIGHT):
                    should_next = True
                elif e.key == pygame.K_ESCAPE:
                    should_skip_all = True

        gesture = self.shared.get_gesture() if hasattr(self.shared, "get_gesture") else None
        now = time.time()

        if gesture == "ThumbUp" and self.last_gesture != "ThumbUp" and now - self.last_advance_time > 0.5:
            should_next = True
            self.last_advance_time = now

        if gesture == "Fist" and self.last_gesture != "Fist" and now - self.last_advance_time > 0.5:
            should_skip_all = True
            self.last_advance_time = now

        self.last_gesture = gesture
        return should_quit, should_skip_all, should_next

    def run(self):
        total_pages = len(self.pages)

        while self.shared.is_running():
            self.clock.tick(getattr(Config, "GAME_FPS", 60))
            should_quit, should_skip_all, should_next = self._handle_input()

            if should_quit:
                self.shared.set_running(False)
                break

            if should_skip_all:
                break

            if should_next:
                self.current_page += 1
                if self.current_page >= total_pages:
                    break

            self._draw_page()
            pygame.display.flip()


def run_intro(shared: SharedState):
    intro = IntroScreen(shared)
    intro.run()
