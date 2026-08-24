# Deployment Guide: ₹0 Production Setup on Oracle Cloud Always Free (OCI Ampere A1)

This guide documents the step-by-step procedure to deploy the **Deepfake-Resistant Provenance & Verification Platform** to an **OCI Always Free VM** (Ampere A1 ARM64) backed by **Cloudflare** for DNS, SSL termination, and CDN caching.

---

## 1. Architecture Overview

```
                      [ Citizens & WhatsApp Users ]
                                    │
                         (Meta WhatsApp Cloud API)
                                    │
                                    ▼
                [ Cloudflare (DNS / Proxied HTTPS / DDoS) ]
                                    │ (Encrypted HTTPS)
                                    ▼
                 [ Oracle Cloud VM (Ampere A1 ARM64) ]
                                    │
            ┌───────────────────────┴───────────────────────┐
            │                 Docker Compose                 │
            │                                               │
            │  ┌───────────────┐     ┌───────────────────┐  │
            │  │ FastAPI (8000)│◄───►│  PostgreSQL 15    │  │
            │  │ (2 workers)   │     │ (provenance_db)   │  │
            │  └───────┬───────┘     │ [postgres_data]   │  │
            │          │             └───────────────────┘  │
            │          ▼             ┌───────────────────┐  │
            │  ┌───────────────┐     │  Redis 7 (Cache)  │  │
            │  │ Next.js (3000)│◄───►│ [redis_data]      │  │
            │  └───────────────┘     └───────────────────┘  │
            │          │                                    │
            │          ▼                                    │
            │  [ uploads_data Volume (Registered Content) ]  │
            └───────────────────────────────────────────────┘
```

---

## 2. Oracle Cloud Always Free VM Setup

1. **Create Compute Instance**:
   - **Image**: Ubuntu 22.04 LTS (aarch64) or Oracle Linux 9 (aarch64).
   - **Shape**: `VM.Standard.A1.Flex` (Ampere A1).
   - **Allocation**: 2 OCPU, 12 GB RAM, 50 GB Boot Volume (all within Always Free tier limits).
   - **SSH Keys**: Download and save your private SSH key.

2. **Security List / Firewall Configuration (VCN)**:
   - In your OCI Console Virtual Cloud Network (VCN) Ingress Rules, allow:
     - `TCP 22`: SSH Access.
     - `TCP 80`: HTTP (for Cloudflare / Certbot).
     - `TCP 443`: HTTPS (for Cloudflare proxied traffic).
     - `TCP 8000`: FastAPI API & Webhook (or proxy via Nginx/Caddy/Cloudflare Tunnel).
     - `TCP 3000`: Next.js Frontend Console.

3. **Install Docker on the OCI VM**:
   ```bash
   # Connect to your VM
   ssh -i /path/to/key ubuntu@<YOUR_OCI_PUBLIC_IP>

   # Install Docker Engine and Docker Compose Plugin
   sudo apt-get update
   sudo apt-get install -y ca-certificates curl gnupg lsb-release
   sudo mkdir -p /etc/apt/keyrings
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
   echo \
     "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
     $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

   sudo apt-get update
   sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
   sudo usermod -aG docker ubuntu
   ```

---

## 3. Clone Repository and Configure Environment

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/your-org/provenance-systems.git ~/provenance-platform
   cd ~/provenance-platform
   ```

2. **Configure Production Environment Variables**:
   ```bash
   cp .env.production.example .env.production
   nano .env.production
   ```
   Fill in the required secrets:
   - `POSTGRES_PASSWORD`: Strong random password.
   - `SECRET_KEY`: Cryptographically secure 32+ character key (`openssl rand -hex 32`).
   - `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_VERIFY_TOKEN`: From your Meta Developer Portal.
   - `NEXT_PUBLIC_API_URL`: `https://your-domain.com/api/v1`.

---

## 4. Launching the Services

Run the deployment script:
```bash
chmod +x deploy.sh backup.sh restore.sh
./deploy.sh
```

To monitor real-time logs:
```bash
docker compose -f docker-compose.prod.yml logs -f
```

---

## 5. Cloudflare DNS & SSL Configuration

1. **Add DNS Records in Cloudflare**:
   - `A` Record: `your-domain.com` $\rightarrow$ `<OCI_PUBLIC_IP>` (Proxy status: **Proxied** 🟧).
   - `A` Record: `api.your-domain.com` $\rightarrow$ `<OCI_PUBLIC_IP>` (Proxy status: **Proxied** 🟧).

2. **SSL/TLS Settings**:
   - Set SSL/TLS Encryption Mode to **Full** or **Full (strict)**.
   - Enable **Always Use HTTPS** and **Automatic HTTPS Rewrites**.

---

## 6. WhatsApp Meta Webhook Setup

1. Go to [Meta for Developers](https://developers.facebook.com/) $\rightarrow$ **WhatsApp** $\rightarrow$ **Configuration**.
2. **Callback URL**: `https://your-domain.com/api/v1/webhook/whatsapp`.
3. **Verify Token**: Enter the exact string set in `WHATSAPP_VERIFY_TOKEN` in `.env.production`.
4. Click **Verify and Save**.
5. Under **Webhook fields**, subscribe to `messages`.

---

## 7. Automated Backups

To schedule daily automated backups of PostgreSQL at 02:00 AM UTC:
```bash
crontab -e
```
Add the following line:
```bash
0 2 * * * cd /home/ubuntu/provenance-platform && ./backup.sh >> /home/ubuntu/provenance-platform/backups/backup.log 2>&1
```
