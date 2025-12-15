import pygame

class PlayerSprite:
    def __init__(self, sprite_path):
        # 讀取整張 sprite sheet
        self.sheet = pygame.image.load(sprite_path).convert_alpha()

        # 每個 frame 的寬高（你的忍者圖片是 128×128）
        self.frame_w = 128
        self.frame_h = 128

        # 定義動作對應的 frame row
        self.anim_map = {
            "run": 0,
            "jump": 1,
            "throw": 2,
            "shield": 3,
        }

        # 每排幾格（如果你的圖集是 4×4，這裡就放 4）
        self.frames_per_row = 4

    def get_frame(self, state, index):
        """取得對應動作的第 index 張 frame"""
        row = self.anim_map.get(state, 0)
        col = index % self.frames_per_row

        x = col * self.frame_w
        y = row * self.frame_h

        frame = self.sheet.subsurface((x, y, self.frame_w, self.frame_h))

        return frame
