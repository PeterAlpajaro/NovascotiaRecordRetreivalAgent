# Nova Scotia Record Retrieval Agent

Email-driven agent for the Senpilot technical challenge.

The agent watches a Gmail inbox for unread requests like:

```text
Hi Agent,
Can you give me Other Documents files from M12205?
Thanks!
```

For matching requests, it opens the Nova Scotia UARB public documents database, downloads up to 10 files from the requested document tab, creates a ZIP archive, and replies to the sender with a concise summary plus the ZIP attachment.

## Stack

- Python
- Playwright for browser automation
- Gmail IMAP/SMTP for email intake and replies
- Optional Kiro Gateway for Anthropic-style request parsing, with deterministic regex fallback
- Docker Compose for VM deployment

## Supported Document Types

- Exhibits
- Key Documents
- Other Documents
- Transcripts
- Recordings

## Local Setup

```bash
cp .env.example .env.production
# Fill in the real values.
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
python -m app.worker --once --env-file .env.production
```

## Docker Deployment

On the VM:

```bash
git clone https://github.com/PeterAlpajaro/NovascotiaRecordRetreivalAgent.git
cd NovascotiaRecordRetreivalAgent
# Add .env.production with Gmail and Kiro values.
docker compose up -d --build
docker compose logs -f agent
```

The Compose file runs its own `kiro-gateway` container and mounts the existing Kiro token directory from the VM:

```text
~/.aws/sso/cache:/home/kiro/.aws/sso/cache:ro
```

No public port is required because the agent polls Gmail.

Kiro parsing is optional. The production demo can run with `ENABLE_LLM_PARSE=false`; to enable it after refreshing Kiro credentials, set `ENABLE_LLM_PARSE=true` and start the profile:

```bash
docker compose --profile kiro up -d --build
```

## Demo Flow

1. Send an unread email to the agent inbox.
2. Watch the VM logs show the request being parsed.
3. Watch Playwright download documents and create a ZIP.
4. Confirm the sender receives a reply with the ZIP attached.

## Notes

- The agent only processes unread emails that contain both a valid matter number and a supported document type.
- Non-matching unread emails are left unread.
- Matching emails are marked read after the agent sends a success or failure reply.
- Secrets belong in `.env.production`, which is intentionally gitignored.
