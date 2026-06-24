from __future__ import annotations

import asyncio
import logging
import re
import shutil
from pathlib import Path

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError, async_playwright

from app.config import Settings
from app.models import AgentRequest, DownloadResult, MatterMetadata, SUPPORTED_DOCUMENT_TYPES

logger = logging.getLogger(__name__)


def _clean_lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def _counts_from_text(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for doc_type in SUPPORTED_DOCUMENT_TYPES:
        pattern = re.compile(rf"{re.escape(doc_type)}\s*[-:]\s*(\d+)", re.IGNORECASE)
        match = pattern.search(text)
        if match:
            counts[doc_type] = int(match.group(1))
    return counts


def _value_after_label(lines: list[str], label: str) -> str:
    lowered = label.lower()
    for index, line in enumerate(lines):
        if line.lower() == lowered:
            for candidate in lines[index + 1 : index + 4]:
                if candidate.lower() not in {"status", "type", "category", "outcome"}:
                    return candidate
    return ""


def _metadata_from_text(matter_number: str, text: str) -> MatterMetadata:
    lines = _clean_lines(text)
    status = ""
    title = ""
    type_name = ""
    category = ""
    date_received = ""
    date_final_submission = ""

    for index, line in enumerate(lines):
        if line.upper() == matter_number.upper():
            window = lines[index + 1 : index + 9]
            dates = [candidate for candidate in window if re.fullmatch(r"\d{2}/\d{2}/\d{4}", candidate)]
            if dates:
                date_received = dates[0]
            if len(dates) > 1:
                date_final_submission = dates[1]

            for candidate in window:
                if " - " in candidate or len(candidate) > 45:
                    title = candidate
                    break

            if title and title in window:
                title_index = window.index(title)
                if title_index > 0:
                    status = window[title_index - 1]

            non_dates = [candidate for candidate in window if candidate not in dates and candidate != title and candidate != status]
            if non_dates:
                category = non_dates[0]
            if dates:
                label_like = {
                    "Back to Search Results",
                    "Matter No",
                    "Status",
                    "Title - Description",
                    "Type",
                    "Category",
                    "Date Received",
                    "Date Final",
                    "Submissions",
                    "Outcome",
                }
                last_date_index = max(window.index(date) for date in dates)
                for candidate in window[last_date_index + 1 :]:
                    if candidate not in label_like:
                        type_name = candidate
                        break
            elif len(non_dates) > 1:
                type_name = non_dates[-1]
            break

    if not title:
        title = _value_after_label(lines, "Title - Description")

    return MatterMetadata(
        matter_number=matter_number,
        title=title,
        status=status,
        type_name=type_name or _value_after_label(lines, "Type"),
        category=category or _value_after_label(lines, "Category"),
        date_received=date_received or _value_after_label(lines, "Date Received"),
        date_final_submission=date_final_submission or _value_after_label(lines, "Date Final Submissions"),
    )


def _safe_filename(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    return cleaned or fallback


async def _click_first_working(locator, description: str, timeout: int = 10000) -> None:
    count = await locator.count()
    last_error: Exception | None = None
    for index in range(count):
        item = locator.nth(index)
        try:
            await item.click(timeout=timeout)
            return
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Could not click {description}: {last_error}")


class UarbClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def download_documents(self, request: AgentRequest) -> DownloadResult:
        download_root = Path(self.settings.download_dir)
        request_dir = download_root / request.matter_number / request.document_type.replace(" ", "_")
        if request_dir.exists():
            shutil.rmtree(request_dir)
        request_dir.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.settings.headless)
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()
            try:
                await page.goto(self.settings.uarb_url, wait_until="domcontentloaded", timeout=90000)
                await self._search_matter(page, request.matter_number)
                await self._open_document_tab(page, request.document_type)

                body_text = await page.locator("body").inner_text(timeout=30000)
                counts = _counts_from_text(body_text)
                metadata = _metadata_from_text(request.matter_number, body_text)

                downloaded_files = await self._download_visible_files(
                    page=page,
                    request_dir=request_dir,
                    limit=self.settings.max_downloads,
                )

                return DownloadResult(
                    request=request,
                    metadata=metadata,
                    counts=counts,
                    downloaded_files=downloaded_files,
                )
            finally:
                await context.close()
                await browser.close()

    async def _search_matter(self, page: Page, matter_number: str) -> None:
        logger.info("Opening UARB matter %s", matter_number)
        await page.wait_for_load_state("domcontentloaded")

        filled = False
        try:
            field = page.locator(".fm_object_254 .text").first
            await field.click(timeout=20000)
            await page.wait_for_timeout(800)
            await page.keyboard.press("ControlOrMeta+A")
            await page.keyboard.press("Backspace")
            await page.keyboard.type(matter_number, delay=100)
            filled = True
        except Exception as exc:
            logger.warning("FileMaker direct matter field failed: %s", exc)

        if not filled:
            raise RuntimeError("Could not find matter search input")

        clicked = False
        try:
            await page.locator(".fm_object_258 button").click(timeout=20000)
            clicked = True
        except Exception as exc:
            logger.warning("Direct matter Search button failed: %s", exc)

        if not clicked:
            raise RuntimeError("Could not click Search button")

        await page.wait_for_timeout(3000)
        try:
            await page.get_by_text(re.compile(re.escape(matter_number), re.IGNORECASE)).first.wait_for(timeout=60000)
        except PlaywrightTimeoutError as exc:
            raise RuntimeError(f"Matter {matter_number} did not load") from exc

    async def _open_document_tab(self, page: Page, document_type: str) -> None:
        logger.info("Opening document tab %s", document_type)
        tab_pattern = re.compile(rf"{re.escape(document_type)}\s*[-:]\s*\d+", re.IGNORECASE)
        candidates = [
            page.get_by_text(tab_pattern),
            page.locator("text=" + document_type),
        ]
        for locator in candidates:
            try:
                await locator.first.click(timeout=20000)
                await page.wait_for_timeout(2000)
                return
            except Exception:
                continue
        raise RuntimeError(f"Could not open tab for {document_type}")

    async def _download_visible_files(self, page: Page, request_dir: Path, limit: int) -> list[Path]:
        files: list[Path] = []
        seen_doc_ids: set[str] = set()
        attempted_doc_ids: set[str] = set()
        stale_scrolls = 0

        while len(files) < limit and stale_scrolls < 5:
            body_text = await page.locator("body").inner_text(timeout=30000)
            visible_doc_ids = [
                line for line in _clean_lines(body_text) if re.fullmatch(r"\d{5,6}", line)
            ]
            buttons = page.get_by_text(re.compile(r"GO GET IT", re.IGNORECASE))
            button_count = await buttons.count()
            logger.info("Visible Go Get It buttons: %s; visible doc ids: %s", button_count, visible_doc_ids[:button_count])

            downloaded_this_view = 0
            for index in range(min(button_count, len(visible_doc_ids))):
                if len(files) >= limit:
                    break

                doc_id = visible_doc_ids[index]
                if doc_id in attempted_doc_ids:
                    continue
                attempted_doc_ids.add(doc_id)

                button = buttons.nth(index)
                try:
                    path = await self._download_one_file(page, button, request_dir, doc_id)
                    actual_id_match = re.match(r"(\d{5,6})", path.name)
                    actual_id = actual_id_match.group(1) if actual_id_match else doc_id
                    if actual_id in seen_doc_ids:
                        logger.info("Skipping duplicate downloaded document %s", actual_id)
                        path.unlink(missing_ok=True)
                        continue
                    seen_doc_ids.add(actual_id)
                    files.append(path)
                    downloaded_this_view += 1
                    logger.info("Downloaded %s", path.name)
                except Exception as exc:
                    logger.warning("Download for doc %s failed: %s", doc_id, exc)

            if len(files) >= limit:
                break

            if downloaded_this_view == 0:
                stale_scrolls += 1
            else:
                stale_scrolls = 0

            await page.mouse.wheel(0, 650)
            await page.wait_for_timeout(1500)

        return files

    async def _download_one_file(self, page: Page, go_get_it_button, request_dir: Path, doc_id: str) -> Path:
        await go_get_it_button.click(timeout=30000)
        await page.locator(".fm-download-button").first.wait_for(timeout=30000)

        async with page.expect_event(
            "request",
            predicate=lambda request: "/dl/" in request.url,
            timeout=30000,
        ) as request_info:
            await page.locator(".fm-download-button").first.click(timeout=10000, force=True)
        request = await request_info.value
        download_url = request.url

        download_page = await page.context.new_page()
        try:
            async with download_page.expect_download(timeout=90000) as download_info:
                try:
                    await download_page.goto(download_url, wait_until="commit", timeout=90000)
                except Exception as exc:
                    # Chromium reports ERR_ABORTED when a top-level navigation
                    # turns into a file download. In this path the download
                    # event is the success signal.
                    if "ERR_ABORTED" not in str(exc):
                        raise
            download = await download_info.value
            filename = _safe_filename(download.suggested_filename, f"{doc_id}.bin")
            path = request_dir / filename
            suffix = 2
            while path.exists():
                path = request_dir / f"{path.stem}-{suffix}{path.suffix}"
                suffix += 1
            await download.save_as(path)
        finally:
            await download_page.close()

        try:
            await page.get_by_text("Close").last.click(timeout=10000)
            await page.locator(".fm-download-button").first.wait_for(state="detached", timeout=10000)
        except Exception as exc:
            logger.warning("Could not close download dialog cleanly: %s", exc)

        return path


def download_documents_sync(settings: Settings, request: AgentRequest) -> DownloadResult:
    return asyncio.run(UarbClient(settings).download_documents(request))
