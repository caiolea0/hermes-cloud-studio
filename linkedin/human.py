"""Human behavior simulation — mouse, typing, scrolling.

All movements use randomized Bezier curves, Gaussian timing distributions,
and natural patterns to avoid detection by behavioral analysis systems.
"""
import asyncio
import math
import random
from typing import List, Tuple, Optional


# --- Bezier Curve Mouse Movement ---

def _bezier_point(t: float, points: List[Tuple[float, float]]) -> Tuple[float, float]:
    """Evaluate cubic Bezier curve at parameter t."""
    n = len(points) - 1
    x, y = 0.0, 0.0
    for i, (px, py) in enumerate(points):
        coeff = math.comb(n, i) * (t ** i) * ((1 - t) ** (n - i))
        x += coeff * px
        y += coeff * py
    return x, y


def _generate_bezier_path(
    start: Tuple[float, float],
    end: Tuple[float, float],
    num_points: int = 30,
    overshoot: float = 0.0,
) -> List[Tuple[int, int]]:
    """Generate natural mouse path using cubic Bezier with random control points."""
    sx, sy = start
    ex, ey = end
    dist = math.hypot(ex - sx, ey - sy)

    spread = max(dist * 0.3, 50)
    cp1 = (
        sx + (ex - sx) * random.uniform(0.2, 0.5) + random.gauss(0, spread * 0.3),
        sy + (ey - sy) * random.uniform(0.1, 0.4) + random.gauss(0, spread * 0.3),
    )
    cp2 = (
        sx + (ex - sx) * random.uniform(0.5, 0.8) + random.gauss(0, spread * 0.2),
        sy + (ey - sy) * random.uniform(0.6, 0.9) + random.gauss(0, spread * 0.2),
    )

    if overshoot > 0:
        dx, dy = ex - sx, ey - sy
        oe = (ex + dx * overshoot, ey + dy * overshoot)
        points_to_target = [_bezier_point(t / num_points, [start, cp1, cp2, oe])
                           for t in range(num_points)]
        correction = [_bezier_point(t / 8, [oe, end]) for t in range(1, 9)]
        path = points_to_target + correction
    else:
        path = [_bezier_point(t / num_points, [start, cp1, cp2, end])
                for t in range(num_points + 1)]

    # hand tremor: ±1-2px random jitter
    tremor_path = []
    for x, y in path:
        jx = x + random.gauss(0, 1.2)
        jy = y + random.gauss(0, 1.2)
        tremor_path.append((round(jx), round(jy)))

    return tremor_path


def _fitts_delays(path: List[Tuple[int, int]], base_speed: float = 1.0) -> List[float]:
    """Fitts's Law velocity profile — accelerate from start, decelerate near target."""
    n = len(path)
    if n <= 1:
        return [0.0]

    delays = []
    for i in range(n):
        t = i / (n - 1)
        # bell curve: fast in middle, slow at start/end
        speed_factor = 0.3 + 2.5 * math.sin(t * math.pi)
        base_delay = random.gauss(12, 4) / speed_factor
        delays.append(max(2, base_delay / base_speed))
    return delays


async def move_mouse_human(page, target_x: int, target_y: int, speed: float = 1.0):
    """Move mouse to target using Bezier curve with Fitts's Law timing."""
    current = await page.evaluate("() => ({x: window._mouseX || 0, y: window._mouseY || 0})")
    start = (current.get("x", random.randint(100, 400)), current.get("y", random.randint(100, 300)))

    should_overshoot = random.random() < 0.12
    overshoot = random.uniform(0.03, 0.08) if should_overshoot else 0.0

    path = _generate_bezier_path(start, (target_x, target_y), overshoot=overshoot)
    delays = _fitts_delays(path, base_speed=speed)

    for (x, y), delay in zip(path, delays):
        await page.mouse.move(x, y)
        await asyncio.sleep(delay / 1000)

    await page.evaluate(f"() => {{ window._mouseX = {target_x}; window._mouseY = {target_y}; }}")


async def click_human(page, selector: str, speed: float = 1.0):
    """Click element with human-like mouse movement and click variance."""
    box = await page.locator(selector).first.bounding_box()
    if not box:
        await page.locator(selector).first.click()
        return

    # don't click dead center — gaussian offset
    x = box["x"] + box["width"] * random.gauss(0.5, 0.12)
    y = box["y"] + box["height"] * random.gauss(0.5, 0.12)
    x = max(box["x"] + 2, min(x, box["x"] + box["width"] - 2))
    y = max(box["y"] + 2, min(y, box["y"] + box["height"] - 2))

    await move_mouse_human(page, int(x), int(y), speed=speed)

    # pre-click micro-pause (human reaction)
    await asyncio.sleep(random.uniform(0.05, 0.2))
    await page.mouse.click(x, y)
    await asyncio.sleep(random.uniform(0.1, 0.3))


# --- Human Typing ---

# Bigram timing: certain character pairs are typed faster
_FAST_BIGRAMS = {"th", "he", "in", "er", "an", "re", "on", "at", "en", "nd", "ti", "es", "or", "te", "of"}
_SLOW_BIGRAMS = {"qz", "xk", "zx", "qw", "jk", "vb"}


async def type_human(page, selector: str, text: str, speed: float = 1.0):
    """Type text with realistic cadence — variable delays, bigram timing, micro-pauses."""
    await click_human(page, selector, speed=speed)
    await asyncio.sleep(random.uniform(0.3, 0.8))

    for i, char in enumerate(text):
        base_delay = random.gauss(120, 35) / 1000  # ~120ms avg

        if i > 0:
            bigram = text[i-1:i+1].lower()
            if bigram in _FAST_BIGRAMS:
                base_delay *= random.uniform(0.5, 0.7)
            elif bigram in _SLOW_BIGRAMS:
                base_delay *= random.uniform(1.5, 2.5)

        if char == " ":
            base_delay += random.uniform(0.02, 0.12)
        elif char in ".,;:!?":
            base_delay += random.uniform(0.05, 0.25)

        # occasional longer pause (thinking)
        if random.random() < 0.03:
            base_delay += random.uniform(0.3, 1.2)

        await page.keyboard.type(char, delay=0)
        await asyncio.sleep(max(0.03, base_delay / speed))


# --- Natural Scrolling ---

async def scroll_human(page, direction: str = "down", amount: int = 300, speed: float = 1.0):
    """Scroll with momentum and variable speed like trackpad/mousewheel."""
    remaining = amount
    while remaining > 0:
        chunk = min(remaining, random.randint(40, 150))
        delta = chunk if direction == "down" else -chunk
        await page.mouse.wheel(0, delta)
        remaining -= chunk

        # momentum: faster at start, slower at end
        progress = 1 - (remaining / amount)
        delay = random.uniform(0.02, 0.08) * (1 + progress * 2)
        await asyncio.sleep(delay / speed)

    # slight over-scroll + correction (15% chance)
    if random.random() < 0.15:
        over = random.randint(20, 60)
        anti = -over if direction == "down" else over
        await page.mouse.wheel(0, -anti if direction == "down" else anti)
        await asyncio.sleep(random.uniform(0.1, 0.3))
        await page.mouse.wheel(0, anti if direction == "down" else -anti)


async def simulate_page_reading(page, min_time: float = 8.0, max_time: float = 45.0, speed: float = 1.0):
    """Simulate reading a page — scroll, pause, scroll more."""
    total_time = random.uniform(min_time, max_time) / speed
    elapsed = 0

    while elapsed < total_time:
        action = random.choices(
            ["scroll", "pause", "move_mouse", "nothing"],
            weights=[0.35, 0.30, 0.20, 0.15],
        )[0]

        if action == "scroll":
            amount = random.randint(100, 400)
            await scroll_human(page, "down", amount, speed=speed)
            wait = random.uniform(1.5, 5.0)
        elif action == "pause":
            wait = random.uniform(2.0, 8.0)
        elif action == "move_mouse":
            vw = await page.evaluate("window.innerWidth")
            vh = await page.evaluate("window.innerHeight")
            x = random.randint(int(vw * 0.1), int(vw * 0.9))
            y = random.randint(int(vh * 0.1), int(vh * 0.9))
            await move_mouse_human(page, x, y, speed=speed)
            wait = random.uniform(0.5, 2.0)
        else:
            wait = random.uniform(1.0, 3.0)

        await asyncio.sleep(wait)
        elapsed += wait


async def random_delay(min_s: float = 3.0, max_s: float = 15.0):
    """Random delay with Gaussian distribution centered between min and max."""
    center = (min_s + max_s) / 2
    sigma = (max_s - min_s) / 4
    delay = max(min_s, min(max_s, random.gauss(center, sigma)))
    await asyncio.sleep(delay)
