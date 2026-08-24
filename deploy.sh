#!/bin/bash
# ============================================================================
# Deepfake-Resistant Provenance System - Production Deployment Script
# Target: OCI Always Free Ampere A1 / Linux ARM64
# ============================================================================

set -euo pipefail

echo "======================================================"
echo " Starting Provenance Verification System Deployment..."
echo "======================================================"

# 1. Environment Check
if [ ! -f .env.production ]; then
    echo "❌ Error: .env.production file not found!"
    echo "👉 Copy .env.production.example to .env.production and configure your variables."
    exit 1
fi

# 2. Check Docker and Docker Compose availability
if ! command -v docker &> /dev/null; then
    echo "❌ Error: Docker is not installed."
    exit 1
fi

COMPOSE_CMD=""
if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose -f docker-compose.prod.yml"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose -f docker-compose.prod.yml"
else
    echo "❌ Error: Docker Compose is not installed."
    exit 1
fi

# 3. Pull / Build Images
echo "📦 Building and updating container images..."
$COMPOSE_CMD build --pull

# 4. Start Services Gracefully
echo "🚀 Starting containers..."
$COMPOSE_CMD up -d --remove-orphans

# 5. Wait for Health Checks
echo "⏳ Waiting for services to become healthy..."
MAX_RETRIES=30
COUNT=0
HEALTHY=false

while [ $COUNT -lt $MAX_RETRIES ]; do
    if curl -sf http://localhost:8000/health > /dev/null; then
        HEALTHY=true
        break
    fi
    echo -n "."
    sleep 2
    COUNT=$((COUNT + 1))
done
echo ""

if [ "$HEALTHY" = true ]; then
    echo "✅ Provenance Platform is healthy and running!"
    echo "   Backend:  http://localhost:8000"
    echo "   Frontend: http://localhost:3000"
    echo "   Health:   http://localhost:8000/health"
else
    echo "⚠️ Warning: Backend health check timed out. Inspecting container logs:"
    $COMPOSE_CMD logs --tail=50 backend
    exit 1
fi

echo "======================================================"
echo " Deployment completed successfully."
echo "======================================================"
