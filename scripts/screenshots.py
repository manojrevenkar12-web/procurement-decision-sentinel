"""Screenshots of the built console. Serve web/dist on port 4173 first: python -m http.server 4173 -d web/dist"""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

OUT = str(Path(__file__).resolve().parents[1] / "docs" / "screenshots")


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-proxy-server"])
        for name, vp, theme, full in [("console", (1440, 900), "light", True), ("console-dark", (1440, 900), "dark", False), ("console-phone", (390, 844), "light", False)]:
            ctx = await b.new_context(viewport={"width": vp[0], "height": vp[1]}, device_scale_factor=2 if name != "console" else 1, color_scheme=theme)
            page = await ctx.new_page()
            await page.goto("http://127.0.0.1:4173/")
            await page.wait_for_selector("ol[aria-label='Why this card exists']")
            await page.wait_for_timeout(1500)
            await page.screenshot(path=f"{OUT}/{name}.png", full_page=full)
            await ctx.close()
        ctx = await b.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        await page.goto("http://127.0.0.1:4173/")
        await page.wait_for_timeout(1200)
        el = await page.query_selector("section[aria-labelledby=stopped-title]")
        await el.screenshot(path=f"{OUT}/stopped.png")
        await b.close()


asyncio.run(main())
