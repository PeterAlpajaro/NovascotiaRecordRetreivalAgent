from __future__ import annotations

import argparse
import logging
import sys
import time

from dotenv import load_dotenv

from app.config import Settings
from app.email_client import GmailClient
from app.request_parser import deterministic_parse, parse_request
from app.responder import build_failure_reply, build_success_reply
from app.state import StateStore
from app.uarb_client import download_documents_sync
from app.zipper import make_zip


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )


logger = logging.getLogger(__name__)


def process_once(settings: Settings) -> int:
    email_client = GmailClient(settings)
    state = StateStore(settings.state_path)
    messages = email_client.fetch_unread()
    logger.info("Fetched %s unread messages", len(messages))

    processed = 0
    for incoming in messages:
        if state.has_processed(incoming.uid):
            continue
        if state.has_ignored(incoming.uid):
            continue

        request = parse_request(f"{incoming.subject}\n\n{incoming.body}", settings)
        if not request:
            if not state.has_ignored(incoming.uid):
                logger.info("Unread UID %s did not match a matter/document request; leaving unread", incoming.uid)
                state.mark_ignored(incoming.uid)
            continue

        logger.info("Processing UID %s: %s %s", incoming.uid, request.matter_number, request.document_type)
        try:
            result = download_documents_sync(settings, request)
            result.archive_path = make_zip(
                result.downloaded_files,
                settings.archive_dir,
                request.matter_number,
                request.document_type,
            )
            subject, body = build_success_reply(result)
            email_client.send_reply(incoming, subject, body, result.archive_path)
        except Exception as exc:
            logger.exception("Failed processing UID %s", incoming.uid)
            subject, body = build_failure_reply(request.matter_number, request.document_type, str(exc))
            email_client.send_reply(incoming, subject, body)

        email_client.mark_seen(incoming.uid)
        state.mark_processed(incoming.uid)
        processed += 1

    return processed


def run_forever(settings: Settings) -> None:
    logger.info("Starting Regulatory Agent for %s", settings.email_address)
    while True:
        try:
            processed = process_once(settings)
            if processed:
                logger.info("Processed %s message(s)", processed)
        except Exception:
            logger.exception("Poll cycle failed")
        time.sleep(settings.poll_interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Nova Scotia UARB email retrieval agent")
    parser.add_argument("--env-file", default=".env.production")
    parser.add_argument("--once", action="store_true", help="Process unread mail once and exit")
    parser.add_argument("--parse", help="Parse a sample email and exit")
    args = parser.parse_args()

    configure_logging()
    load_dotenv(args.env_file)
    settings = Settings.from_env()

    if args.parse:
        parsed = deterministic_parse(args.parse)
        print(parsed)
        return

    if args.once:
        process_once(settings)
    else:
        run_forever(settings)


if __name__ == "__main__":
    main()
