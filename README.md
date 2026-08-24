# Deepfake-Resistant Provenance & Verification Platform

A national-scale digital provenance and cryptographic verification platform allowing authorized government publishers to sign authentic media (images, audio, video, documents, text) and enabling citizens to verify media authenticity through WhatsApp and web consoles.

---

## Architecture & Verification Engine

1. **Multi-Mechanism Verification Pipeline**:
   - **SHA-256 Exact Hash Match**: Cryptographic identity verification.
   - **Perceptual Hashing (pHash / dHash)**: Visual near-duplicate detection resistant to social media compression.
   - **Acoustic Fingerprinting (MFCC + Chroma)**: Audio speech/broadcast verification.
   - **Ed25519 Digital Signatures**: Cryptographic non-repudiation for government publishers.
   - **Immutable Hash-Chain Ledger**: Chronologically chained and tamper-evident registration blocks.
2. **Citizen-Facing WhatsApp Integration**:
   - "Verdict First, Proof on Tap" design.
   - Meta Cloud API v18.0 Webhook integration.
   - Interactive reply buttons for cryptographically verified evidence and PIB fact-check portal routing.

---

## Technology Stack

- **Backend**: FastAPI 0.104, Uvicorn (ASGI), Python 3.12, Pydantic v2.
- **Database**: PostgreSQL 15 (SQLAlchemy 2.0 ORM).
- **Caching & Security**: Redis 7 (sliding window rate limiting, token blacklisting).
- **Computer Vision & Audio**: OpenCV, Pillow, ImageHash, Librosa, SoundFile, FFmpeg.
- **Frontend**: Next.js 16, React 19, Tailwind CSS, Lucide React.
- **Production Target**: Oracle Cloud Always Free (Ampere A1 ARM64 / 2 OCPU / 12 GB RAM) behind Cloudflare.

---

## Local Development Setup

### 1. Prerequisites
- Docker & Docker Compose
- Python 3.11 or 3.12
- Node.js 18+ or 20+

### 2. Start Infrastructure
```bash
# Start PostgreSQL and Redis containers
docker compose up -d
```

### 3. Backend Setup
```bash
cd backend
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 4. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

---

## Running Automated Tests

The test suite runs with complete test database isolation against `provenance_test_db`:
```bash
cd backend
python -m pytest -v
```

---

## Production Deployment

For full production deployment instructions on Oracle Cloud Always Free (Ampere A1) and Cloudflare, see:
- [Deployment Guide](docs/DEPLOYMENT.md)
- [Troubleshooting Guide](docs/TROUBLESHOOTING.md)
- [Production Environment Template](.env.production.example)

### Quick Production Launch
```bash
cp .env.production.example .env.production
# Edit .env.production with your production credentials
chmod +x deploy.sh backup.sh restore.sh
./deploy.sh
```
