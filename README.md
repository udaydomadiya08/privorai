# Local Privacy Firewall for LLMs

Privacy is enforced locally. Intelligence is outsourced safely.

This project implements a production-oriented hybrid LLM firewall that guarantees raw user input stays on-device. Every prompt flows through a local privacy brain before anything can reach a cloud model.

## What It Does

- Detects sensitive data with hybrid PII detection
  - Regex and heuristics by default
  - Presidio + spaCy integration when enabled
- Rewrites sensitive content into context-preserving abstractions
- Uses session-consistent synthetic placeholders for entities like people and contact details
- Refines sanitized prompts locally through Ollama before cloud usage
- Supports `hybrid`, `strict`, and `fully_local` privacy modes
- Shows original input, sanitized outbound input, and transformation details in the UI
- Keeps placeholder mappings ephemeral and in-memory only
- Accepts local filesystem files or uploaded files and parses them on-device before sanitization
- Supports local OCR for images and local transcription for audio/video when optional dependencies are installed
- Performs a final outbound privacy inspection before cloud delivery and can automatically block cloud calls on residual risk
- Supports async directory jobs for large local ingestion tasks
- Can require an API key for operational endpoints
- Can store encrypted local audit snapshots of sanitized-only outbound context
- Reports job progress for long-running directory ingestion

## Architecture

```text
Browser UI (local only)
        |
        v
FastAPI Input Handler
        |
        v
PII Detection Engine
  - regex
  - heuristics
  - optional Presidio/spaCy
        |
        v
Smart Sanitization Engine
  - semantic abstraction
  - synthetic placeholders
  - session-consistent mapping
        |
        v
Local LLM Prompt Refiner (Ollama)
        |
        +--------------------------+
        |                          |
        v                          v
Secure Cloud LLM Interface      Fully Local LLM Answering
        |
        v
Response Processing Layer
```

## Quick Start

1. Create an environment and install dependencies.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Copy environment settings.

```bash
cp .env.example .env
```

3. Optional: install a spaCy model if you want richer local NLP.

```bash
python -m spacy download en_core_web_sm
```

4. Optional: run Ollama locally with a lightweight model.

```bash
ollama pull mistral:7b-instruct
```

5. Start the app.

```bash
uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Container Deployment

This repo includes a Docker Compose deployment with:

- `firewall-app` running FastAPI behind Uvicorn
- `reverse-proxy` running Nginx
- health checks
- persistent encrypted audit volume
- TLS-ready certificate mount points

### Local Compose Run

1. Create a runtime env file.

```bash
cp /Users/uday/Downloads/privorai/.env.example /Users/uday/Downloads/privorai/.env
```

2. Start the stack.

```bash
docker compose up --build
```

3. Open:

- [http://127.0.0.1:8080](http://127.0.0.1:8080)

### TLS Setup

The default Compose stack is HTTP-only so it boots safely without certificates.

To enable TLS:

1. Mount your certs into [deploy/certs](/Users/uday/Downloads/privorai/deploy/certs):

- `fullchain.pem`
- `privkey.pem`

2. Copy [firewall-https.conf.example](/Users/uday/Downloads/privorai/deploy/nginx/tls/firewall-https.conf.example) into `deploy/nginx/conf.d/`.

3. Expose `443` in your reverse proxy deployment or compose override.

### Production Compose Override

This repo includes [docker-compose.production.yml](/Users/uday/Downloads/privorai/docker-compose.production.yml) for a stricter deployment profile.

Run it with:

```bash
docker compose -f docker-compose.yml -f docker-compose.production.yml up --build
```

The production overlay adds:

- `80` and `443` host bindings
- TLS certificate mounts
- a hardened HTTPS Nginx config
- request rate limiting for `/api/`
- connection limiting for `/api/`
- stricter security headers including CSP

### Production Env Template

See [deploy/env/.env.production.example](/Users/uday/Downloads/privorai/deploy/env/.env.production.example).

## Modes

- `hybrid`
  - balanced anonymization
  - local sanitization + cloud reasoning
- `strict`
  - stronger abstraction and broader generalization
  - local sanitization + cloud reasoning
- `fully_local`
  - no external API calls
  - local sanitization + local LLM response generation

## Security Guarantees

- Raw input never leaves the local process
- Raw file bytes never leave the local process
- No sensitive prompts are logged
- Placeholder mappings stay in memory and expire automatically
- Cloud calls use only sanitized prompts
- Web search queries are always generalized before any provider call
- A final outbound guard re-checks refined prompts before any cloud use
- Audit snapshots never contain raw input and are encrypted at rest when enabled

## File Ingestion

The system now supports local parsing for:

- Plain text and code files
- PDF
- DOCX
- PPTX
- XLSX
- CSV and TSV
- JSON and XML
- Images with OCR
- Audio/video with local Whisper transcription
- Recursive folder ingestion with file manifests

Parsing happens locally. Extracted text is then run through the same privacy pipeline as typed chat.

There are two file flows:

- Upload through the UI or `POST /api/chat/file`
- Reference a local path with `POST /api/chat/path`
- Analyze a directory with `POST /api/chat/directory`
- Queue a large directory run with `POST /api/jobs/directory` and poll `GET /api/jobs/{job_id}`

Job status now includes:

- `progress_percent`
- `current_step`
- `items_processed`
- `total_items`
- `current_item_label`
- `current_item_parser`
- `eta_seconds`
- `recent_items`

Note: "any file type" in the absolute sense is not realistic without format-specific parsers. This build handles common business and developer formats well and rejects unsupported binary formats safely instead of risking leakage.

## Robust Local Media Support

- Image OCR uses `pytesseract` locally
- Audio/video transcription uses `openai-whisper` locally
- Large documents are chunked locally before sanitization
- Folder ingestion builds a local manifest and processes supported files up to a safe cap
- Every parsed file returns an artifact summary so the UI can show exactly what was processed

## Outbound Guard

Before any cloud call, the system now:

- trims prompts to a maximum outbound size budget
- re-checks for residual email, phone, address, identifier, path, and strict-mode placeholder risks
- blocks cloud routing and falls back to local answering when configured to do so

Relevant settings:

- `MAX_OUTBOUND_PROMPT_CHARS`
- `BLOCK_CLOUD_ON_RESIDUAL_RISK`
- `MAX_DIRECTORY_FILES`

## API Protection

Optional API-key protection is available for chat, file, job, audit, and session reset endpoints.

RBAC is now supported with two practical roles:

- `user`: chat, file, directory, jobs, and session reset
- `admin`: everything in `user` plus audit snapshot access

Relevant settings:

- `API_AUTH_ENABLED`
- `API_AUTH_TOKEN`
- `API_USER_TOKEN`
- `API_ADMIN_TOKEN`

When enabled, send:

```text
X-API-Key: <your token>
```

Role behavior:

- `API_USER_TOKEN` can use core product endpoints but cannot read audits
- `API_ADMIN_TOKEN` can use core product endpoints and audit endpoints
- `API_AUTH_TOKEN` remains supported as a legacy full-access token for compatibility

## Admin Console

The built-in web UI now includes an admin console for:

- recent background job browsing
- live job detail inspection
- audit snapshot listing
- audit snapshot detail viewing

To use it:

- enter an admin-scoped API key in the UI
- use `Refresh Jobs`
- use `Refresh Audits`

## Privacy-Safe Logging

Structured logging is available for operations and incident response without exposing raw prompts.

Logs include metadata such as:

- request id
- request path and method
- timing
- privacy mode
- provider used
- residual risk outcome
- counts for detections, transformations, artifacts, and chunks

Logs do not include:

- raw user input
- raw file content
- sanitized prompt text
- answer text

Relevant settings:

- `PRIVACY_LOGGING_ENABLED`
- `PRIVACY_LOG_LEVEL`

## Encrypted Audit Snapshots

The system can persist sanitized-only audit snapshots locally for review and incident analysis.

Snapshot contents:

- sanitized input
- refined prompt
- provider used
- residual-risk result
- file artifacts

Snapshot contents never include raw user input or raw file bytes.

Relevant settings:

- `AUDIT_SNAPSHOTS_ENABLED`
- `AUDIT_SNAPSHOTS_DIR`
- `AUDIT_ENCRYPTION_KEY`

Generate a Fernet key with:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## CI And Validation

This repo includes a GitHub Actions workflow in [ci.yml](/Users/uday/Downloads/privorai/.github/workflows/ci.yml) that:

- installs Python dependencies
- installs OCR and media system packages
- compiles the source tree
- runs the test suite
- validates the Docker image build
- validates both Compose configurations

For local validation, run:

```bash
bash /Users/uday/Downloads/privorai/scripts/validate.sh
```

## Release Pipeline

This repo also includes a release workflow in [release.yml](/Users/uday/Downloads/privorai/.github/workflows/release.yml).

What it does:

- builds a multi-arch container image
- tags images from Git refs and commit SHA
- publishes to GitHub Container Registry
- attaches OCI metadata labels

Release triggers:

- push a tag like `v1.0.0`
- manually run the workflow from GitHub Actions

Published image format:

- `ghcr.io/<owner>/<repo>:v1.0.0`
- `ghcr.io/<owner>/<repo>:sha-<commit>`
- `ghcr.io/<owner>/<repo>:latest` on the default branch

## Environment Notes

- `ENABLE_PRESIDIO=true` enables Presidio-backed entity detection when dependencies are present.
- `ENABLE_WEB_SEARCH=true` enables optional Tavily search if `TAVILY_API_KEY` is set.
- If no cloud API key is configured, hybrid and strict modes safely fall back to local answering instead of leaking raw input.

## Tests

```bash
pytest
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
