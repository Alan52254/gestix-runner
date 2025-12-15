# credits_screen.py
# -----------------------------
# GestiX Runner — Victory / Credits Screen
# - Displays scrolling credits after Game Victory (Score >= 4000)
# - Usage:
#     from credits_screen import run_credits
#     run_credits(shared)
# -----------------------------

import pygame
import time
from gestix_mediapipe2 import SharedState, Config

# 為了保持風格一致，我們使用與 Intro 相同的漸層背景邏輯
def create_gradient_surface(w, h, c1, c2):
    surf = pygame.Surface((w, h))
    for y in range(h):
        r = c1[0] + (c2[0] - c1[0]) * y // h
        g = c1[1] + (c2[1] - c1[1]) * y // h
        b = c1[2] + (c2[2] - c1[2]) * y // h
        pygame.draw.line(surf, (r, g, b), (0, y), (w, y))
    return surf

class CreditsScreen:
    def __init__(self, shared: SharedState):
        self.shared = shared
        
        # 初始化 Pygame (防止意外未初始化)
        pygame.init()
        self.screen = pygame.display.set_mode((Config.SCREEN_W, Config.SCREEN_H))
        pygame.display.set_caption("GestiX Runner — Victory")
        
        self.clock = pygame.time.Clock()
        
        # 背景顏色 (使用稍微不同的色調代表黎明/勝利，例如深紫到深藍)
        self.bg_color_top = (15, 10, 30)
        self.bg_color_bot = (40, 20, 60)
        self.bg = create_gradient_surface(
            Config.SCREEN_W, Config.SCREEN_H, 
            self.bg_color_top, self.bg_color_bot
        )

        # 字型設定
        self.font_title = pygame.font.SysFont("arial", 50, bold=True)
        self.font_header = pygame.font.SysFont("arial", 32, bold=True)
        self.font_body = pygame.font.SysFont("arial", 24)
        
        # 結局內容設定
        self.content = [
            ("VICTORY", "title"),
            ("", "space"),
            ("MISSION ACCOMPLISHED", "header"),
            ("The Boss has fallen.", "body"),
            ("The dark rift seals shut, and the ink", "body"),
            ("monsters dissolve into shadows.", "body"),
            ("", "space"),
            ("Morning light pierces through the", "body"),
            ("shrine once more.", "body"),
            ("Peace has returned to the mountain.", "body"),
            ("", "space"),
            ("", "space"),
            ("DEVELOPMENT TEAM", "header"),
            ("Alan", "body"),
            ("Neil", "body"),
            ("", "space"),
            ("GAME ENGINE & DESIGN", "header"),
            ("Pygame Framework", "body"),
            ("MediaPipe Gesture Control", "body"),
            ("", "space"),
            ("SPECIAL THANKS", "header"),
            ("To all the players who", "body"),
            ("mastered the art of gestures.", "body"),
            ("", "space"),
            ("", "space"),
            ("THANK YOU FOR PLAYING!", "title"),
        ]

        # 預先渲染所有文字到一個長畫布上 (效能優化)
        self.scroll_surface = self._render_all_text()
        self.scroll_y = Config.SCREEN_H  # 從螢幕最下方開始
        self.scroll_speed = 1.5          # 捲動速度
        
        self.last_gesture = None
        self.running = True

    def _render_all_text(self):
        """計算總高度並繪製所有文字"""
        spacing_map = {
            "title": 80,
            "header": 50,
            "body": 35,
            "space": 40
        }
        
        # 1. 計算總高度
        total_height = 0
        for text, style in self.content:
            total_height += spacing_map.get(style, 30)
            
        # 2. 建立長畫布
        surf = pygame.Surface((Config.SCREEN_W, total_height), pygame.SRCALPHA)
        
        # 3. 繪製文字
        current_y = 0
        for text, style in self.content:
            if style == "space":
                current_y += spacing_map["space"]
                continue
                
            if style == "title":
                font = self.font_title
                color = (255, 215, 0) # 金色
            elif style == "header":
                font = self.font_header
                color = (200, 200, 255) # 淡藍色
            else: # body
                font = self.font_body
                color = (230, 230, 230) # 白色
                
            render_txt = font.render(text, True, color)
            rect = render_txt.get_rect(center=(Config.SCREEN_W // 2, current_y + 20))
            surf.blit(render_txt, rect)
            
            current_y += spacing_map.get(style, 30)
            
        return surf

    def _handle_input(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.shared.set_running(False)
                self.running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    self.running = False
        
        # 取得手勢
        gesture = self.shared.get_gesture() if hasattr(self.shared, "get_gesture") else None
        
        # 手勢互動：比讚可以加速捲動 (快轉)
        if gesture == "ThumbUp":
            self.scroll_speed = 5.0
        else:
            self.scroll_speed = 1.5
            
        # 手勢互動：握拳直接結束片尾
        if gesture == "Fist" and self.last_gesture != "Fist":
             self.running = False

        self.last_gesture = gesture

    def run(self):
        # 如果有背景音樂，建議在這裡播放勝利音樂
        # pygame.mixer.music.load("victory_theme.mp3")
        # pygame.mixer.music.play(-1)

        while self.running and self.shared.is_running():
            dt = self.clock.tick(60)
            self._handle_input()
            
            # 更新捲動位置
            self.scroll_y -= self.scroll_speed
            
            # 判斷結束條件：當文字完全捲出螢幕上方，等待幾秒後自動結束
            if self.scroll_y < -self.scroll_surface.get_height() - 50:
                time.sleep(2) # 停頓一下讓玩家回味
                self.running = False

            # 繪製
            self.screen.blit(self.bg, (0, 0))
            self.screen.blit(self.scroll_surface, (0, self.scroll_y))
            
            # 繪製提示
            hint_txt = pygame.font.SysFont("arial", 16).render(
                "ThumbUp: Fast Forward   Fist/Esc: Skip", True, (100, 100, 120)
            )
            self.screen.blit(hint_txt, (10, Config.SCREEN_H - 25))
            
            pygame.display.flip()

def run_credits(shared: SharedState):
    credits = CreditsScreen(shared)
    credits.run()