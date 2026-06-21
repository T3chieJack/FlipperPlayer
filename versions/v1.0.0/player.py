from __future__ import annotations

import io
import os
import re
import time
import warnings
import ctypes
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
warnings.filterwarnings("ignore", message="pkg_resources is deprecated as an API.*", category=UserWarning)
if os.name == "nt":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("T3chieJack.FlipperPlayer")
    except Exception:
        pass
import pygame
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
ANIMATIONS = ROOT / "Animations"
ASSETS = ROOT / "Assets"

DESIGN_W, DESIGN_H = 930, 550
MIN_W, MIN_H = 760, 460
SS = 2

ORANGE = (254, 138, 44)
WHITE = (255, 247, 240)
BACKGROUND = (15, 12, 10)
PANEL = (22, 18, 15)
GRID = (43, 27, 17)
BUTTON = (40, 21, 9)
SELECTOR = (73, 29, 0)
LCD_DARK = (91, 51, 19)
LCD_LIGHT = (180, 140, 108)
MUTED = (155, 80, 26)
MENU_BG = (12, 9, 7)
MENU_HOVER = (91, 40, 8)

try:
    PIXEL_FONT = ImageFont.truetype(str(ASSETS / "PixelifySans.ttf"), 16)
except OSError:
    PIXEL_FONT = ImageFont.load_default_imagefont()



class DesktopPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def desktop_cursor() -> tuple[int, int]:
    if os.name == "nt":
        point = DesktopPoint()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
        return point.x, point.y
    return pygame.mouse.get_pos()
def frame_number(path: Path) -> int:
    match = re.search(r"(\d+)$", path.stem)
    return int(match.group(1)) if match else 0


def parse_meta(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values.setdefault(key.strip().lower(), value.strip())
    return values


@dataclass
class Animation:
    folder: Path
    title: str
    order: list[int]
    fps: float
    width: int
    height: int

    @classmethod
    def load(cls, folder: Path) -> "Animation | None":
        meta_path = folder / "meta.txt"
        if not meta_path.exists():
            return None
        metadata = parse_meta(meta_path)
        available = {frame_number(path) for path in folder.glob("frame_*.png")}
        try:
            requested = [int(value) for value in metadata.get("frames order", "").split()]
            order = [value for value in requested if value in available] or sorted(available)
            fps = max(0.1, float(metadata.get("frame rate", "2")))
            width = int(metadata.get("width", "128"))
            height = int(metadata.get("height", "64"))
        except ValueError:
            return None
        if not order:
            return None
        title = re.sub(r"_128x\d+$", "", folder.name).replace("_", " ")
        return cls(folder, title, order, fps, width, height)

    def frame_path(self, step: int) -> Path:
        return self.folder / f"frame_{self.order[step % len(self.order)]}.png"


def discover_animations() -> list[Animation]:
    if not ANIMATIONS.exists():
        return []
    result: list[Animation] = []
    for folder in sorted(ANIMATIONS.iterdir(), key=lambda item: item.name.lower()):
        if folder.is_dir() and (animation := Animation.load(folder)):
            result.append(animation)
    return result


class Player:
    def __init__(self) -> None:
        pygame.init()
        self.animations = discover_animations()
        if not self.animations:
            raise RuntimeError(f"No valid animations found in {ANIMATIONS}")

        pygame.display.set_caption("FlipperPlayer")
        try:
            pygame.display.set_icon(pygame.image.load(str(ROOT / "logo.png")))
        except pygame.error:
            pass
        self.flags = pygame.RESIZABLE | pygame.NOFRAME
        self.dpi_scale = 1.0
        if os.name == "nt":
            try:
                self.dpi_scale = ctypes.windll.user32.GetDpiForSystem() / 96.0
            except Exception:
                pass
        initial_size = (round(DESIGN_W * self.dpi_scale), round(DESIGN_H * self.dpi_scale))
        self.screen = pygame.display.set_mode(initial_size, self.flags)
        self.native_icons: dict[int, int] = {}
        self.apply_windows_icon()
        self.clock = pygame.time.Clock()

        self.animation_index = 0
        self.frame_step = 0
        self.last_frame_time = time.perf_counter()
        self.flipper_ui = True
        self.running = True
        self.dragging = False
        self.resizing = False
        self.drag_offset = (0, 0)
        self.resize_start = (0, 0, DESIGN_W, DESIGN_H)

        self.menu_open = False
        self.menu_scroll = 0
        self.menu_rows: list[tuple[pygame.Rect, int]] = []
        self.hovered_animation = -1

        self.frame_sources: dict[Path, pygame.Surface] = {}
        self.svg_cache: dict[tuple[int, int], pygame.Surface] = {}
        self.text_cache: dict[tuple[str, int, tuple[int, int, int], float], pygame.Surface] = {}
        self.close_svg = (ASSETS / "close.svg").read_bytes()
        self.minimize_svg = (ASSETS / "minimize.svg").read_bytes()
        self.flipper_svg = (ASSETS / "flipper.svg").read_bytes()

        try:
            from pygame._sdl2 import Window
            self.window = Window.from_display_module()
        except Exception:
            self.window = None

    def apply_windows_icon(self) -> None:
        if os.name != "nt":
            return
        hwnd = pygame.display.get_wm_info().get("window")
        if not hwnd:
            return
        icon_path = str((ASSETS / "logo.ico").resolve())
        for icon_type, size in ((0, 32), (1, 64)):
            handle = self.native_icons.get(icon_type)
            if not handle:
                handle = ctypes.windll.user32.LoadImageW(
                    None, icon_path, 1, size, size, 0x0010
                )
                if handle:
                    self.native_icons[icon_type] = handle
            if handle:
                ctypes.windll.user32.SendMessageW(hwnd, 0x0080, icon_type, handle)
    @property
    def animation(self) -> Animation:
        return self.animations[self.animation_index]

    def xy(self, x: float, y: float, scale: int = 1) -> tuple[int, int]:
        width, height = self.screen.get_size()
        return round(x * width / DESIGN_W * scale), round(y * height / DESIGN_H * scale)

    def rect(self, x: float, y: float, width: float, height: float, scale: int = 1) -> pygame.Rect:
        px, py = self.xy(x, y, scale)
        pw, ph = self.xy(width, height, scale)
        return pygame.Rect(px, py, pw, ph)

    def svg_surface(self, source: bytes, width: int, height: int) -> pygame.Surface:
        """Rasterize the SVG at native output resolution using SDL_image."""
        source = source.replace(b'class="st0"', b'fill="url(#SVGID_1_)"').replace(b'class="st1"', b'fill="#FE8A2C"')
        viewbox = re.search(rb'viewBox="\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)', source)
        if not viewbox:
            original = pygame.image.load(io.BytesIO(source), "asset.svg").convert_alpha()
            return pygame.transform.smoothscale(original, (width, height))
        base_width, base_height = float(viewbox.group(1)), float(viewbox.group(2))
        svg = re.sub(rb'width="[^"]+"', f'width="{width}"'.encode(), source, count=1)
        svg = re.sub(rb'height="[^"]+"', f'height="{height}"'.encode(), svg, count=1)
        root = re.search(rb'<svg\b[^>]*>', svg)
        transform = f'<g transform="scale({width/base_width},{height/base_height})">'.encode()
        if root:
            svg = svg[:root.end()] + transform + svg[root.end():]
            svg = svg.replace(b'</svg>', b'</g></svg>', 1)
        surface = pygame.image.load(io.BytesIO(svg), "asset.svg").convert_alpha()
        if surface.get_size() != (width, height):
            surface = pygame.transform.smoothscale(surface, (width, height))
        return surface
    def flipper_surface(self, width: int, height: int) -> pygame.Surface:
        key = (width, height)
        if key not in self.svg_cache:
            high = self.svg_surface(self.flipper_svg, width * SS, height * SS)
            self.svg_cache[key] = pygame.transform.smoothscale(high, (width, height))
            if len(self.svg_cache) > 10:
                first = next(iter(self.svg_cache))
                if first != key:
                    del self.svg_cache[first]
        return self.svg_cache[key]

    def pixel_text(self, text: str, height: int, color: tuple[int, int, int] = WHITE,
                   stretch: float = 1.0) -> pygame.Surface:
        key = (text, height, color, stretch)
        if key in self.text_cache:
            return self.text_cache[key]
        box = PIXEL_FONT.getbbox(text)
        line_box = PIXEL_FONT.getbbox("Ag")
        source_width = max(1, box[2] - box[0])
        source_height = max(1, line_box[3] - line_box[1])
        image = Image.new("RGBA", (source_width, source_height))
        ImageDraw.Draw(image).text((-box[0], -line_box[1]), text, font=PIXEL_FONT,
                                   fill=color + (255,))
        width = max(1, round(source_width / source_height * height * stretch))
        alpha = image.getchannel("A").point(lambda value: 255 if value >= 112 else 0)
        solid = Image.new("RGBA", image.size, color + (255,))
        solid.putalpha(alpha)
        image = solid.resize((width, height), Image.Resampling.NEAREST)
        surface = pygame.image.fromstring(image.tobytes(), image.size, "RGBA").convert_alpha()
        self.text_cache[key] = surface
        return surface

    @staticmethod
    def blit_anchor(target: pygame.Surface, source: pygame.Surface, position: tuple[int, int],
                    anchor: str = "center") -> pygame.Rect:
        rect = source.get_rect()
        if anchor == "midleft":
            rect.midleft = position
        elif anchor == "midright":
            rect.midright = position
        elif anchor == "topleft":
            rect.topleft = position
        else:
            rect.center = position
        target.blit(source, rect)
        return rect

    def draw_background(self, high: pygame.Surface) -> None:
        width, height = high.get_size()
        # Subtle vertical Figma-like tonal change, not a flat rectangle patched at edges.
        for y in range(height):
            t = y / max(1, height - 1)
            color = (round(16 + 4 * t), round(13 + 3 * t), round(11 + 2 * t))
            pygame.draw.line(high, color, (0, y), (width, y))
        grid_x, grid_y = self.xy(38, 38, SS)
        offset_x, offset_y = self.xy(10, 12, SS)
        clip = self.rect(0, 0, DESIGN_W, DESIGN_H, SS).inflate(-3 * SS, -3 * SS)
        high.set_clip(clip)
        for x in range(offset_x, width, max(1, grid_x)):
            pygame.draw.line(high, GRID, (x, clip.top), (x, clip.bottom), SS)
        for y in range(offset_y, height, max(1, grid_y)):
            pygame.draw.line(high, GRID, (clip.left, y), (clip.right, y), SS)
        high.set_clip(None)

    def rounded(self, target: pygame.Surface, color: tuple[int, ...], rect: pygame.Rect,
                radius: int, width: int = 0) -> None:
        pygame.draw.rect(target, color, rect, width=width, border_radius=radius)

    def draw_chrome(self, high: pygame.Surface) -> tuple[pygame.Rect, bool]:
        self.draw_background(high)
        s = SS
        outer = self.rect(0, 0, DESIGN_W, DESIGN_H, s)
        self.rounded(high, ORANGE, outer, 4 * s, 3 * s)

        panel = self.rect(22, 44, 887, 434, s)
        overlay = pygame.Surface(high.get_size(), pygame.SRCALPHA)
        self.rounded(overlay, PANEL + (180,), panel, 4 * s)
        high.blit(overlay, (0, 0))
        self.rounded(high, ORANGE, panel, 4 * s, 3 * s)


        toggle = self.rect(34, 60, 149, 45, s)
        self.rounded(high, BUTTON, toggle, 4 * s)
        self.rounded(high, ORANGE, toggle, 4 * s, 3 * s)
        check = self.rect(153, 72, 20, 22, s)
        self.rounded(high, ORANGE if self.flipper_ui else (103, 51, 14), check, 3 * s)

        selector = self.rect(22, 495, 887, 43, s)
        self.rounded(high, SELECTOR, selector, 3 * s)
        self.rounded(high, ORANGE, selector, 3 * s, 3 * s)

        if self.flipper_ui:
            shell_rect = self.rect(185, 141, 560, 243, s)
            shell = self.flipper_surface(shell_rect.width, shell_rect.height)
            high.blit(shell, shell_rect)
            animation_rect = self.rect(323, 175, 212, 114)
        else:
            animation_rect = self.rect(198, 120, 555, 295)
        return animation_rect, self.flipper_ui

    def frame_source(self, path: Path) -> pygame.Surface:
        if path not in self.frame_sources:
            image = Image.open(path).convert("L")
            pixels = image.load()
            output = Image.new("RGB", image.size, LCD_DARK)
            out = output.load()
            for y in range(image.height):
                for x in range(image.width):
                    if pixels[x, y] >= 128:
                        out[x, y] = LCD_LIGHT
            self.frame_sources[path] = pygame.image.fromstring(
                output.tobytes(), output.size, "RGB"
            ).convert()
        return self.frame_sources[path]

    def draw_animation(self, target: pygame.Surface, rect: pygame.Rect, radius: int) -> None:
        source = self.frame_source(self.animation.frame_path(self.frame_step))
        # pygame.transform.scale is nearest-neighbour. Never smoothscale this layer.
        scaled = pygame.transform.scale(source, rect.size)
        if radius > 0:
            # Smooth only the four-pixel clipping edge; the frame pixels remain untouched.
            mask_high = pygame.Surface((rect.width * SS, rect.height * SS), pygame.SRCALPHA)
            pygame.draw.rect(mask_high, (255, 255, 255, 255), mask_high.get_rect(),
                             border_radius=radius * SS)
            mask = pygame.transform.smoothscale(mask_high, rect.size)
            scaled = scaled.convert_alpha()
            scaled.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        target.blit(scaled, rect)

    def draw_text_and_icons(self, target: pygame.Surface) -> None:
        width, height = target.get_size()
        sx, sy = width / DESIGN_W, height / DESIGN_H
        scale = min(sx, sy)
        pos = lambda x, y: (round(x * sx), round(y * sy))

        title = self.pixel_text("FlipperPlayer", max(11, round(16 * scale)), stretch=1.05)
        self.blit_anchor(target, title, pos(29, 28), "midleft")
        toggle = self.pixel_text("Flipper UI", max(13, round(19 * scale)), stretch=0.88)
        self.blit_anchor(target, toggle, pos(45, 83), "midleft")
        if self.flipper_ui:
            block = max(3, round(3 * scale))
            for cell_x, cell_y in ((157, 81), (159, 83), (161, 85), (163, 83),
                                   (165, 81), (167, 79), (169, 77)):
                px, py = pos(cell_x, cell_y)
                pygame.draw.rect(target, WHITE, (px, py, block, block))
        playing = self.pixel_text(f"Playing: {{{self.animation.title}}}",
                                  max(12, round(17 * scale)), stretch=1.18)
        self.blit_anchor(target, playing, pos(465, 516))
        signature = self.pixel_text("T3chieJack", max(9, round(11 * scale)), MUTED, 1.0)
        self.blit_anchor(target, signature, pos(895, 464), "midright")
        version = self.pixel_text("v1.0.0", max(6, round(7 * scale)), (78, 43, 22), 1.0)
        self.blit_anchor(target, version, pos(895, 450), "midright")

        icon_w, icon_h = max(14, round(20 * scale)), max(14, round(20 * scale))
        close = pygame.transform.smoothscale(
            self.svg_surface(self.close_svg, icon_w * SS, icon_h * SS), (icon_w, icon_h)
        )
        minimize = pygame.transform.smoothscale(
            self.svg_surface(self.minimize_svg, icon_w * SS, icon_h * SS), (icon_w, icon_h)
        )
        self.blit_anchor(target, minimize, pos(851, 29))
        self.blit_anchor(target, close, pos(886, 29))

    def draw_menu(self, target: pygame.Surface) -> None:
        if not self.menu_open:
            self.menu_rows.clear()
            return
        width, height = target.get_size()
        sx, sy = width / DESIGN_W, height / DESIGN_H
        scale = min(sx, sy)
        pos = lambda x, y: (round(x * sx), round(y * sy))
        menu_rect = self.rect(190, 126, 550, 340)

        overlay_high = pygame.Surface((width * SS, height * SS), pygame.SRCALPHA)
        mr = pygame.Rect(menu_rect.x * SS, menu_rect.y * SS,
                         menu_rect.width * SS, menu_rect.height * SS)
        self.rounded(overlay_high, MENU_BG + (252,), mr, 7 * SS)
        self.rounded(overlay_high, ORANGE + (255,), mr, 7 * SS, 2 * SS)
        target.blit(pygame.transform.smoothscale(overlay_high, (width, height)), (0, 0))

        heading = self.pixel_text("SELECT ANIMATION", max(12, round(16 * scale)), ORANGE, 1.05)
        self.blit_anchor(target, heading, (menu_rect.x + round(18 * sx),
                                           menu_rect.y + round(24 * sy)), "midleft")
        visible = 10
        maximum = max(0, len(self.animations) - visible)
        self.menu_scroll = max(0, min(self.menu_scroll, maximum))
        row_height = round(28 * sy)
        row_x = menu_rect.x + round(10 * sx)
        row_width = menu_rect.width - round(20 * sx)
        first_y = menu_rect.y + round(48 * sy)
        mouse = pygame.mouse.get_pos()
        self.menu_rows.clear()
        self.hovered_animation = -1
        for visible_index in range(visible):
            animation_index = self.menu_scroll + visible_index
            if animation_index >= len(self.animations):
                break
            row = pygame.Rect(row_x, first_y + visible_index * row_height,
                              row_width, row_height - 1)
            if row.collidepoint(mouse):
                pygame.draw.rect(target, MENU_HOVER, row, border_radius=max(2, round(3 * scale)))
                self.hovered_animation = animation_index
            animation = self.animations[animation_index]
            label = self.pixel_text(f"{animation.title}  ·  {animation.fps:g} FPS  ·  {len(set(animation.order))} FRAMES",
                                    max(10, round(13 * scale)), WHITE, 1.0)
            self.blit_anchor(target, label, (row.x + round(10 * sx), row.centery), "midleft")
            self.menu_rows.append((row, animation_index))

        if maximum:
            track = pygame.Rect(menu_rect.right - round(10 * sx), first_y,
                                max(2, round(3 * sx)), visible * row_height)
            pygame.draw.rect(target, (68, 35, 17), track, border_radius=track.width // 2)
            thumb_h = max(round(28 * sy), round(track.height * visible / len(self.animations)))
            thumb_y = track.y + round((track.height - thumb_h) * self.menu_scroll / maximum)
            pygame.draw.rect(target, ORANGE, (track.x, thumb_y, track.width, thumb_h),
                             border_radius=track.width // 2)

    def render(self) -> None:
        width, height = self.screen.get_size()
        high = pygame.Surface((width * SS, height * SS), pygame.SRCALPHA)
        animation_rect, rounded = self.draw_chrome(high)
        final = pygame.transform.smoothscale(high, (width, height))
        self.draw_animation(final, animation_rect, radius=7 if rounded else 4)
        self.draw_text_and_icons(final)
        self.draw_menu(final)
        self.screen.blit(final, (0, 0))
        pygame.display.flip()

    def select_animation(self, index: int) -> None:
        self.animation_index = index
        self.frame_step = 0
        self.last_frame_time = time.perf_counter()
        self.menu_open = False

    def handle_click(self, position: tuple[int, int]) -> None:
        if self.menu_open:
            for row, index in self.menu_rows:
                if row.collidepoint(position):
                    self.select_animation(index)
                    return
            self.menu_open = False
            return
        if self.rect(865, 10, 42, 36).collidepoint(position):
            self.running = False
        elif self.rect(828, 10, 38, 36).collidepoint(position):
            pygame.display.iconify()
        elif self.rect(34, 60, 149, 45).collidepoint(position):
            self.flipper_ui = not self.flipper_ui
        elif self.rect(22, 495, 887, 43).collidepoint(position):
            self.menu_open = True
            self.menu_scroll = max(0, min(self.animation_index,
                                           len(self.animations) - 10))

    def update_animation(self) -> None:
        now = time.perf_counter()
        interval = 1.0 / self.animation.fps
        elapsed = now - self.last_frame_time
        if elapsed >= interval:
            count = max(1, int(elapsed / interval))
            self.frame_step = (self.frame_step + count) % len(self.animation.order)
            self.last_frame_time += count * interval

    def run(self) -> None:
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.VIDEORESIZE:
                    size = (max(round(MIN_W * self.dpi_scale), event.w),
                            max(round(MIN_H * self.dpi_scale), event.h))
                    self.screen = pygame.display.set_mode(size, self.flags)
                    self.apply_windows_icon()
                    self.svg_cache.clear()
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.menu_open:
                            self.menu_open = False
                        else:
                            self.running = False
                    elif self.menu_open and event.key in (pygame.K_UP, pygame.K_DOWN):
                        delta = -1 if event.key == pygame.K_UP else 1
                        self.menu_scroll = max(0, min(self.menu_scroll + delta,
                                                      len(self.animations) - 10))
                elif event.type == pygame.MOUSEWHEEL and self.menu_open:
                    self.menu_scroll = max(0, min(self.menu_scroll - event.y,
                                                  len(self.animations) - 10))
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    position = event.pos
                    if position[1] <= self.xy(0, 44)[1] and not self.rect(828, 10, 79, 36).collidepoint(position):
                        self.dragging = True
                        if self.window:
                            wx, wy = self.window.position
                            mx, my = desktop_cursor()
                            self.drag_offset = (mx - wx, my - wy)
                    else:
                        self.handle_click(position)
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    self.dragging = False
                elif event.type == pygame.MOUSEMOTION and self.dragging and self.window:
                    mx, my = desktop_cursor()
                    offset_x, offset_y = self.drag_offset
                    self.window.position = (mx - offset_x, my - offset_y)

            self.update_animation()
            self.render()
            self.clock.tick(60)
        pygame.quit()


def main() -> None:
    try:
        Player().run()
    except Exception as error:
        pygame.quit()
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("FlipperPlayer", str(error))
        root.destroy()


if __name__ == "__main__":
    main()






























