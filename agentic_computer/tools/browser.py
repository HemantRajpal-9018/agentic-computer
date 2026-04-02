"""Browser automation tool powered by Playwright.

Provides a high-level interface for navigating pages, clicking elements,
typing text, capturing screenshots, extracting text, and running arbitrary
JavaScript.  The browser is lazily initialised on first use and cleaned up
via :pymethod:`cleanup`.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

from agentic_computer.config import get_settings
from agentic_computer.tools.registry import BaseTool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


class BrowserTool(BaseTool):
    """Playwright-based browser automation tool.

    The underlying browser instance is created lazily on the first call to
    any action method and reused for subsequent calls.  Call :pymethod:`cleanup`
    to close the browser and release resources.
    """

    def __init__(self) -> None:
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._context: Any | None = None
        self._page: Any | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # BaseTool interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return (
            "Automate a Chromium browser: navigate to URLs, click elements, "
            "type text, capture screenshots, extract page text, and execute JavaScript."
        )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters={
                "action": {
                    "type": "string",
                    "description": (
                        "The browser action to perform.  One of: navigate, click, "
                        "type_text, screenshot, extract_text, execute_js."
                    ),
                },
                "url": {"type": "string", "description": "URL for navigate action."},
                "selector": {
                    "type": "string",
                    "description": "CSS selector for click / type_text actions.",
                },
                "text": {"type": "string", "description": "Text for type_text action."},
                "script": {"type": "string", "description": "JavaScript for execute_js action."},
            },
            required_params=["action"],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Dispatch to the appropriate browser action."""
        action = kwargs.get("action", "")
        dispatch = {
            "navigate": self._handle_navigate,
            "click": self._handle_click,
            "type_text": self._handle_type_text,
            "screenshot": self._handle_screenshot,
            "extract_text": self._handle_extract_text,
            "execute_js": self._handle_execute_js,
        }
        handler = dispatch.get(action)
        if handler is None:
            return ToolResult(
                success=False,
                error=f"Unknown browser action '{action}'. Valid actions: {', '.join(dispatch)}",
            )
        try:
            return await handler(**kwargs)
        except Exception as exc:
            logger.exception("Browser action '%s' failed", action)
            return ToolResult(success=False, error=str(exc))

    # ------------------------------------------------------------------
    # Public action methods (also usable directly)
    # ------------------------------------------------------------------

    async def navigate(self, url: str) -> ToolResult:
        """Navigate to *url* and return the page title and a text snapshot.

        Args:
            url: The URL to load.

        Returns:
            ToolResult with output containing ``title`` and ``text`` keys.
        """
        page = await self._ensure_page()
        settings = get_settings()
        try:
            await page.goto(url, timeout=settings.browser.timeout)
            await page.wait_for_load_state("domcontentloaded")
            title = await page.title()
            text = await page.inner_text("body")
            # Truncate very large pages to avoid blowing up context windows.
            max_chars = 50_000
            if len(text) > max_chars:
                text = text[:max_chars] + "\n... [truncated]"
            return ToolResult(success=True, output={"title": title, "text": text, "url": url})
        except Exception as exc:
            return ToolResult(success=False, error=f"Navigation failed: {exc}")

    async def click(self, selector: str) -> ToolResult:
        """Click the element matching *selector*.

        Args:
            selector: A CSS selector that identifies the element.
        """
        page = await self._ensure_page()
        try:
            await page.click(selector, timeout=get_settings().browser.timeout)
            return ToolResult(success=True, output=f"Clicked: {selector}")
        except Exception as exc:
            return ToolResult(success=False, error=f"Click failed on '{selector}': {exc}")

    async def type_text(self, selector: str, text: str) -> ToolResult:
        """Type *text* into the element matching *selector*.

        Args:
            selector: CSS selector of the target input or textarea.
            text: The string to type.
        """
        page = await self._ensure_page()
        try:
            await page.fill(selector, text, timeout=get_settings().browser.timeout)
            return ToolResult(success=True, output=f"Typed text into '{selector}'")
        except Exception as exc:
            return ToolResult(success=False, error=f"Type failed on '{selector}': {exc}")

    async def screenshot(self) -> ToolResult:
        """Capture the current viewport as a base64-encoded PNG.

        Returns:
            ToolResult with ``output`` set to the base64 image string.
        """
        page = await self._ensure_page()
        try:
            raw = await page.screenshot(type="png")
            b64 = base64.b64encode(raw).decode("utf-8")
            return ToolResult(success=True, output=b64)
        except Exception as exc:
            return ToolResult(success=False, error=f"Screenshot failed: {exc}")

    async def extract_text(self) -> ToolResult:
        """Extract all visible text from the current page.

        Returns:
            ToolResult whose ``output`` is the extracted text string.
        """
        page = await self._ensure_page()
        try:
            text = await page.inner_text("body")
            return ToolResult(success=True, output=text)
        except Exception as exc:
            return ToolResult(success=False, error=f"Text extraction failed: {exc}")

    async def execute_js(self, script: str) -> ToolResult:
        """Evaluate *script* in the page context and return its result.

        Args:
            script: A JavaScript expression or snippet.
        """
        page = await self._ensure_page()
        try:
            result = await page.evaluate(script)
            return ToolResult(success=True, output=result)
        except Exception as exc:
            return ToolResult(success=False, error=f"JS execution failed: {exc}")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def cleanup(self) -> None:
        """Close the browser, context, and Playwright instance."""
        async with self._lock:
            if self._page:
                await self._page.close()
                self._page = None
            if self._context:
                await self._context.close()
                self._context = None
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

    # ------------------------------------------------------------------
    # Private: dispatch helpers
    # ------------------------------------------------------------------

    async def _handle_navigate(self, **kwargs: Any) -> ToolResult:
        url = kwargs.get("url")
        if not url:
            return ToolResult(success=False, error="'url' is required for navigate action")
        return await self.navigate(url)

    async def _handle_click(self, **kwargs: Any) -> ToolResult:
        selector = kwargs.get("selector")
        if not selector:
            return ToolResult(success=False, error="'selector' is required for click action")
        return await self.click(selector)

    async def _handle_type_text(self, **kwargs: Any) -> ToolResult:
        selector = kwargs.get("selector")
        text = kwargs.get("text")
        if not selector or text is None:
            return ToolResult(
                success=False,
                error="'selector' and 'text' are required for type_text action",
            )
        return await self.type_text(selector, text)

    async def _handle_screenshot(self, **kwargs: Any) -> ToolResult:
        return await self.screenshot()

    async def _handle_extract_text(self, **kwargs: Any) -> ToolResult:
        return await self.extract_text()

    async def _handle_execute_js(self, **kwargs: Any) -> ToolResult:
        script = kwargs.get("script")
        if not script:
            return ToolResult(success=False, error="'script' is required for execute_js action")
        return await self.execute_js(script)

    # ------------------------------------------------------------------
    # Private: lazy browser setup
    # ------------------------------------------------------------------

    async def _ensure_page(self) -> Any:
        """Return the active page, creating the browser if necessary."""
        async with self._lock:
            if self._page is not None:
                return self._page

            from playwright.async_api import async_playwright

            settings = get_settings()
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=settings.browser.headless,
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            self._page = await self._context.new_page()
            return self._page
