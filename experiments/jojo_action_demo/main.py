from __future__ import annotations

from pathlib import Path

import pygame as pg

try:
    from . import constants
except ImportError:  # execução direta: python main.py
    import constants

ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "Assets"


def _natural_sort(path: Path):
    suffix = path.stem.rsplit("-", 1)[-1]
    try:
        return (0, int(suffix))
    except ValueError:
        return (1, path.name.lower())


def load_animation_images(directory: Path, prefix: str):
    """Carrega frames em ordem numérica, sem exigir diretório de trabalho específico."""
    paths = sorted(directory.glob(f"{prefix}*.png"), key=_natural_sort)
    return [pg.image.load(str(path)).convert_alpha() for path in paths]


class Player:
    def __init__(self, screen_width: int, screen_height: int, assets: dict):
        self.x = float(constants.START_X)
        self.screen_width = screen_width
        self.floor_y = float(screen_height - 6)
        self.speed = float(constants.VEL * 60)
        self.assets = assets
        renderables = [
            value
            for key, value in assets.items()
            if key != "background"
        ]
        self.max_sprite_width = max(
            image.get_width()
            for value in renderables
            for image in (value if isinstance(value, list) else [value])
        )
        self.facing = 1
        self.velocity_y = 0.0
        self.jump_speed = -500.0
        self.gravity = 1500.0
        self.walk_elapsed = 0.0
        self.attack_until = 0.0

    @property
    def jumping(self):
        return self.velocity_y != 0.0 or self.floor_y < self._base_floor

    @property
    def _base_floor(self):
        return float(self.assets["standing_right"].get_height() + constants.GROUND_TOP)

    def start_jump(self):
        if not self.jumping:
            self.velocity_y = self.jump_speed

    def start_attack(self, now: float):
        self.attack_until = now + 0.34

    def update(self, dt: float, keys, now: float, crouch_pressed: bool):
        moving = False
        if keys[pg.K_LEFT] and not keys[pg.K_RIGHT]:
            self.x -= self.speed * dt
            self.facing = -1
            moving = True
        elif keys[pg.K_RIGHT] and not keys[pg.K_LEFT]:
            self.x += self.speed * dt
            self.facing = 1
            moving = True

        self.x = max(0.0, min(self.x, self.screen_width - self.max_sprite_width))

        if self.jumping:
            self.velocity_y += self.gravity * dt
            self.floor_y += self.velocity_y * dt
            if self.floor_y >= self._base_floor:
                self.floor_y = self._base_floor
                self.velocity_y = 0.0

        self.walk_elapsed = self.walk_elapsed + dt if moving else 0.0
        self.crouching = bool(crouch_pressed and not self.jumping)
        self.attacking = bool(now < self.attack_until)

    def draw(self, screen, now: float):
        if self.jumping:
            image = self.assets["jump_right" if self.facing > 0 else "jump_left"]
        elif self.crouching:
            image = self.assets["crouch_right" if self.facing > 0 else "crouch_left"]
        elif self.attacking:
            image = self.assets["attack"]
        else:
            frames = self.assets["walk_right" if self.facing > 0 else "walk_left"]
            if frames:
                image = frames[int(self.walk_elapsed * 10) % len(frames)]
            else:
                image = self.assets["standing_right" if self.facing > 0 else "standing_left"]

        target = image.get_rect()
        target.bottomleft = (round(self.x), round(self.floor_y))
        screen.blit(image, target)


class ActionDemo:
    def __init__(self):
        pg.init()
        self.screen_width = int(constants.SCREEN_WIDTH)
        self.screen_height = int(constants.SCREEN_HEIGHT)
        self.screen = pg.display.set_mode((self.screen_width, self.screen_height))
        pg.display.set_caption("JoJo Action Demo")
        self.clock = pg.time.Clock()
        self.font = pg.font.Font(None, 21)
        self.running = True
        self.audio_ready = False
        self.attack_sound = None
        self.music_error = None
        self._init_audio()
        self.assets = self._load_assets()
        self.player = Player(self.screen_width, self.screen_height, self.assets)

    def _init_audio(self):
        try:
            if pg.mixer.get_init() is None:
                pg.mixer.init()
            pg.mixer.set_num_channels(max(16, pg.mixer.get_num_channels()))
            self.audio_ready = True
        except pg.error:
            return

        music = ROOT / "bg-music.mp3"
        try:
            if music.is_file():
                pg.mixer.music.load(str(music))
                pg.mixer.music.set_volume(0.25)
                pg.mixer.music.play(-1)
        except pg.error as exc:
            self.music_error = str(exc)

        attack = ROOT / "ora.mp3"
        try:
            if attack.is_file():
                self.attack_sound = pg.mixer.Sound(str(attack))
                self.attack_sound.set_volume(0.35)
        except pg.error:
            self.attack_sound = None

    def _load_assets(self):
        required = {
            "standing_right": ASSET_DIR / "standing-right.png",
            "standing_left": ASSET_DIR / "standing-left.png",
            "jump_right": ASSET_DIR / "jump-right.png",
            "jump_left": ASSET_DIR / "jump-left.png",
            "crouch_right": ASSET_DIR / "crouch-right.png",
            "crouch_left": ASSET_DIR / "crouch-left.png",
            "attack": ROOT / "attacking.png",
            "background": ROOT / "game_bg.png",
        }
        missing = [str(path) for path in required.values() if not path.is_file()]
        if missing:
            raise FileNotFoundError("Assets ausentes:\n" + "\n".join(missing))

        assets = {name: pg.image.load(str(path)).convert_alpha() for name, path in required.items()}
        background = assets["background"]
        assets["background"] = pg.transform.smoothscale(background, (self.screen_width, self.screen_height))
        assets["walk_right"] = load_animation_images(ASSET_DIR, "going-right-")
        assets["walk_left"] = load_animation_images(ASSET_DIR, "going-left-")
        return assets

    def _events(self):
        for event in pg.event.get():
            if event.type == pg.QUIT:
                self.running = False
            elif event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    self.running = False
                elif event.key == pg.K_UP:
                    self.player.start_jump()
                elif event.key == pg.K_SPACE:
                    self.player.start_attack(pg.time.get_ticks() / 1000.0)
                    if self.attack_sound is not None:
                        self.attack_sound.play()

    def _draw(self, now: float):
        self.screen.blit(self.assets["background"], (0, 0))
        self.player.draw(self.screen, now)
        hud = pg.Surface((self.screen_width, 30), pg.SRCALPHA)
        hud.fill((0, 0, 0, 145))
        self.screen.blit(hud, (0, self.screen_height - 30))
        label = self.font.render("←/→ mover   ↑ pular   ↓ agachar   Espaço atacar   Esc sair", True, (255, 255, 255))
        self.screen.blit(label, (12, self.screen_height - 23))
        pg.display.flip()

    def run(self):
        while self.running:
            dt = min(self.clock.tick(int(constants.FPS)) / 1000.0, 0.05)
            self._events()
            now = pg.time.get_ticks() / 1000.0
            keys = pg.key.get_pressed()
            self.player.update(dt, keys, now, keys[pg.K_DOWN])
            self._draw(now)

    def close(self):
        if self.audio_ready:
            try:
                pg.mixer.music.stop()
                pg.mixer.quit()
            except pg.error:
                pass
        pg.quit()


def main():
    game = None
    try:
        game = ActionDemo()
        game.run()
    except (FileNotFoundError, OSError, pg.error) as exc:
        print(f"Não foi possível iniciar a demo: {exc}")
    finally:
        if game is not None:
            game.close()
        else:
            pg.quit()


if __name__ == "__main__":
    main()
