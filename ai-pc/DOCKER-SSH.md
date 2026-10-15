# AI PC over SSH · Ubuntu + Docker

Run the commands in this guide on the **Ubuntu AI PC through SSH**, unless explicitly labelled as a command for your local Windows PC or Raspberry Pi. You do not need a desktop on the AI PC. Keep the Pi kiosk stopped until its connection check succeeds.

## 1. Download the code on the AI PC

```bash
sudo apt-get update
sudo apt-get install -y git
cd ~
git clone https://github.com/digitalsgisb/facescanpk.git
cd ~/facescanpk/ai-pc
```

If you already cloned this repository on the AI PC, use the existing checkout instead:

```bash
cd ~/facescanpk
git pull --ff-only
cd ai-pc
```

## 2. Install/check Docker

```bash
bash install-docker-ubuntu.sh
```

This keeps an existing Docker + Compose installation. On a new Ubuntu machine it installs Docker Engine and the Compose plugin from Docker's official apt repository and enables Docker at boot. It does not remove existing container packages. If Docker exists without Compose or conflicting packages prevent installation, follow the matching [official Ubuntu installation](https://docs.docker.com/engine/install/ubuntu/) or [Compose plugin instructions](https://docs.docker.com/compose/install/linux/) rather than removing an existing installation blindly.

## 3. Prepare persistent storage

From `~/facescanpk/ai-pc`:

```bash
mkdir -p runtime
```

For the **first Docker setup only**, write your SSH user's numeric UID/GID so the container can write the mounted folder without running as root:

```bash
printf 'ATTENDANCE_UID=%s\nATTENDANCE_GID=%s\n' "$(id -u)" "$(id -g)" > .env
```

Keep an existing `.env` when updating; it may contain your chosen bind address/port. `runtime/` holds the real SQLite database, uploaded photos and backups. `data/` is mounted read-only for initial employee seeding. The image build excludes both runtime data and the private employee seed.

## 4. Choose empty installation or existing company data

**New empty installation:** skip to step 5. Add employees through the app later.

**Keep the current 173 employees/photos/attendance:** transfer the private data before starting the container. The public GitHub clone deliberately contains no employee data.

On your **local Windows PC**, send the separately supplied private archive to the AI PC. Replace `SSH_USER` and `AI_PC_IP` with the same username/address you use for SSH:

```powershell
scp "C:\Users\haffizol\Desktop\Project\Smart Attendance\packages\Smart-Attendance-Company-Data-PRIVATE.zip" SSH_USER@AI_PC_IP:~/attendance-private.zip
```

Back in the **AI PC SSH terminal**, for a new destination with no existing attendance database:

```bash
cd ~/facescanpk/ai-pc
sudo apt-get install -y unzip
unzip ~/attendance-private.zip -d ~/attendance-private
cp -a ~/attendance-private/ai-pc/runtime/. ./runtime/
cp ~/attendance-private/ai-pc/data/employees.json ./data/employees.json
```

Do not run those restore commands over an existing live database. If the destination already has attendance, stop its container, make a backup and follow the intentional restore instructions in the README. Restore a complete database into an empty runtime folder, without stale WAL/SHM files from another database. Files should be owned by the SSH user whose UID/GID is in `.env`.

The private archive is a snapshot from when it was created. It includes the existing admin login/device registrations; it does not contain later changes automatically. It does not contain the Pi's face enrollments or offline queue. Keep those on the Pi.

## 5. Build and start the container

```bash
cd ~/facescanpk/ai-pc
sudo docker compose up -d --build
sudo docker compose ps
curl --fail http://127.0.0.1:8765/api/health
```

The first build downloads Node/Python images, builds React and installs Python dependencies inside Docker. You do not need Node.js or the app's Python dependencies installed on the host. Keep port 8765 free of another attendance service. After startup, SSH can be disconnected; Compose uses `restart: unless-stopped`, and the Docker daemon is enabled at boot.

If the container fails to start:

```bash
sudo docker compose logs --tail=100 attendance
```

## 6. Create the administrator from SSH

For an empty installation:

```bash
sudo docker compose exec attendance python manage.py init-admin
```

Enter a new password of at least 12 characters twice at the hidden prompts. No password is passed in a command argument or stored in `.env`. The command refuses to overwrite an existing administrator.

If you restored the company database, **skip this step** and use the existing administrator password. The terminal command is needed for headless setup because initial browser-based admin creation is restricted to local clients; do not weaken that restriction to make Docker work.

## 7. Create a kiosk token from SSH

```bash
sudo docker compose exec attendance python manage.py create-kiosk --name "Port Klang Pi"
```

Copy the token shown once privately. It is a kiosk token, not your administrator password. It can also be created/revoked from System settings after signing in from the Pi browser. If an existing Pi token still works after restoring its database, you may keep it instead of creating another.

## 8. Connect the Pi

The service address is **`http://AI_PC_IP:8765`**, where `AI_PC_IP` is the reachable LAN address used for SSH. Do not enter `0.0.0.0`, `127.0.0.1` or a Docker bridge address on the Pi.

In a **Pi terminal**, inside `/home/wblsugihara` using the kiosk's existing Python environment:

```bash
python3 configure_kiosk.py
python3 configure_kiosk.py --check
sudo systemctl start attendance-kiosk
sudo systemctl status attendance-kiosk
```

At the setup prompts, enter the AI PC service address and the kiosk token from step 7. The AI PC service must be reachable from the Pi's company network. Docker-published ports have their own networking/firewall behaviour; configure access on your company network rather than exposing this service to the internet. See [Docker firewall guidance](https://docs.docker.com/engine/install/ubuntu/#firewall-limitations).

## 9. Show the HDMI board

On the Pi browser, open `http://AI_PC_IP:8765`, sign in with the admin password, move the browser to HDMI, select Live board → TV fullscreen. Keep Python on DSI-1 (800×480); the HDMI board is 1366×768 at (800,0).

## 10. Update later

Create a consistent private backup before updating:

```bash
cd ~/facescanpk/ai-pc
sudo docker compose exec attendance python manage.py backup --output "runtime/backups/pre-update-$(date +%Y%m%d-%H%M%S).zip"
git pull --ff-only
sudo docker compose up -d --build
sudo docker compose ps
```

This preserves the bind-mounted `runtime/` directory and `.env`. Never delete `runtime/` to fix a failed build. If Git reports local source changes, preserve/resolve them first. A plain Docker restart does not rebuild changed React code; use the build command above.

## HTTP / company HTTPS

The supplied Compose file serves HTTP on port 8765 for a reachable company network. For your existing HTTPS setup, place it behind the company's trusted reverse proxy, configure its upstream to this service and use the HTTPS address on both Pi and browser. Optionally set `ATTENDANCE_BIND=127.0.0.1` in `.env` when the reverse proxy runs on this host, then recreate the container. Keep certificate keys outside GitHub. Only expose the direct LAN port where it is actually needed for this company network.

Local Docker image execution could not be checked in the Windows development workspace; verify the image build and health check on the Ubuntu host. The terminal administration and attendance logic have automated tests.
