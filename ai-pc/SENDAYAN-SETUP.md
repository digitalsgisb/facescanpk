# Sendayan: update, connect the Pi, and share the TV layout

Use the existing AI PC as the shared attendance server for both plants. Update it first. The Pi runs the camera/kiosk; the React dashboard and database run on the AI PC. A Pi Git pull alone cannot update the dashboard.

These steps apply after this code has been committed and pushed to `origin/main`. Local development edits are not downloaded by `git pull` until published. Run each command only after the previous command succeeds.

## 1. Update the AI PC

In the AI PC's SSH terminal, for the existing Ubuntu Docker installation:

```bash
cd /srv/apps/facescan_pk
if [ -f ai-pc/compose.yaml ]; then cd ai-pc; fi
test -f compose.yaml
git status --short
```

If Git lists local changes, preserve/reconcile them before pulling. Keep the current `.env`, `data/` and `runtime/`. Back up, update and rebuild:

```bash
sudo docker compose exec attendance python manage.py backup --output "runtime/backups/pre-sendayan-$(date +%Y%m%d-%H%M%S).zip"
git pull --ff-only origin main
sudo docker compose up -d --build
sudo docker compose ps
curl --fail http://127.0.0.1:3800/api/health
```

Retry the health check once the container is healthy. A native Python installation must use the existing service's stop/start procedure and rebuild React; see [the AI PC README](README.md#git-pull-update--native-python-installation).

## 2. Set up Sendayan on the AI PC dashboard

Sign in with the all-plants administrator/developer account.

1. Open **Employees**, filter location to **SENDAYAN**, and confirm the roster. If absent, preview/import the Sendayan employee file using the existing [plant rollout procedure](PLANT-ROLLOUT.md). Do not restore another plant's database over the live server.
2. Check each employee's ID, Position, department and production line. Position text is displayed as entered; it is not guessed. Set Sendayan teams **C / D / N** and configure their hours in **Shifts**.
3. Under **System settings → Staff permissions and photo retention**, create/update `sendayan-admin` with role Administrator, location `SENDAYAN`, and your chosen private password.
4. Under **System settings → Add connection**, create a **Raspberry Pi attendance kiosk** connection named `Sendayan Pi`. Assign its location to `SENDAYAN` (also available under **Connection plant access**). Copy the device token when shown. Use a separate connection from the Port Klang Pi.
5. Keep Port Klang's kiosk assigned to `PORT KLANG`. Do not leave either kiosk's plant blank on a shared server.

## 3. Confirm the server is reachable from Sendayan

Use the attendance service address that is actually reachable from Sendayan. For the existing HTTPS installation, check from the Pi:

```bash
curl --fail https://pkattendance.sugidigital.org/api/health
```

Continue only if this returns the attendance health response. A private Port Klang LAN IP is reachable from Sendayan only when your network/VPN routes it. If you use a reachable AI PC LAN/VPN address, Docker normally uses `http://AI_PC_IP:3800`; native Python normally uses port `8765`. Replace `AI_PC_IP` with the actual reachable address. Do not use `127.0.0.1` on the Pi for the remote AI PC. If a proxy requires an extra browser sign-in, it must also permit the authenticated kiosk API connection.

## 4. Pull the Pi code

Use the Sendayan Pi's terminal. If it already has a checkout:

```bash
cd ~/facescanpk
git status --short
git pull --ff-only origin main
```

If `~/facescanpk` does not exist yet, clone once instead:

```bash
cd ~
git clone https://github.com/digitalsgisb/facescanpk.git
```

Preserve any local changes if Git refuses the pull. Do not use `git reset --hard` or delete the kiosk data to update.

## 5. Stop the existing Sendayan kiosk and copy the code

First let pending scans finish. For a terminal launch, press **Ctrl+C** in that kiosk terminal and wait for its camera to close. If it uses the existing service, stop it instead:

```bash
sudo systemctl stop attendance-kiosk
```

Use the **actual Sendayan live folder containing its working `face.py` and `database/`**. `/home/wblsugihara` is the known Port Klang path; do not assume Sendayan uses the same username. In the block below, replace `/absolute/path/to/sendayan-kiosk` before running. Activate the kiosk's existing Python environment first if it uses one.

```bash
(
set -e
umask 077
LIVE=/absolute/path/to/sendayan-kiosk
SOURCE="$HOME/facescanpk/raspberry-pi"
test -d "$LIVE"
test -f "$LIVE/face.py"
test -f "$SOURCE/face.py"
files=(face.py kiosk_config.py kiosk_keyboard.py kiosk_touch.py kiosk_instance.py
       kiosk_transport.py kiosk_vision.py configure_kiosk.py configure_display.py
       run_kiosk.sh kiosk.env.example 1.png)
for file in "${files[@]}"; do test -f "$SOURCE/$file"; done
backup="$HOME/attendance-backups/sendayan-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup"
for item in database kiosk-runtime kiosk.env "${files[@]}"; do
    if [ -e "$LIVE/$item" ]; then cp -a -- "$LIVE/$item" "$backup/"; fi
done
for file in "${files[@]}"; do cp -- "$SOURCE/$file" "$LIVE/$file"; done
printf 'Code copied. Private backup: %s\n' "$backup"
)
```

This copies named code/assets only. Existing face models, `database/`, `kiosk-runtime/` and `kiosk.env` stay in place. A checkout used directly as the live installation does not need the copy: stop its kiosk, back up the same private files, pull in that checkout, and run from its `raspberry-pi/` folder. A completely new Pi still needs the existing working camera/InsightFace environment and models described in the [Pi README](../raspberry-pi/README.md#screen-and-dependencies).

## 6. Configure the Sendayan connection

Change to that same live folder:

```bash
cd /absolute/path/to/sendayan-kiosk
python3 configure_kiosk.py
```

Enter the reachable AI PC base address (for example `https://pkattendance.sugidigital.org`, without `/api`), then the **Sendayan kiosk token** at the hidden prompt. It saves `kiosk.env`. For later updates with a working connection, keep that configuration and run only the check:

```bash
python3 configure_kiosk.py --check
```

Confirm **Connected successfully** and the expected active Sendayan employee count. Zero means the Sendayan roster/location needs checking; do not assume a successful network connection means the correct roster. Employee records come from the PC; face enrollment stays local to this Pi.

## 7. Start and verify

For a manual launch, run from the touchscreen desktop terminal:

```bash
bash run_kiosk.sh
```

For an existing service installation, start only the service instead:

```bash
sudo systemctl start attendance-kiosk
sudo systemctl status attendance-kiosk --no-pager
```

1. Confirm the camera is online on the touchscreen. Keep one kiosk instance running.
2. Register Sendayan faces locally: **Register face → choose employee → Save face**. Dashboard profile photos are separate from recognition enrollment.
3. On HDMI, open the same attendance server address in the browser. Sign in as `sendayan-admin`, open **Live board**, then **TV fullscreen**. The plant-scoped account keeps this display on Sendayan. An all-plants account can choose the plant in the board header.
4. Check one approved test employee's supervised scan and the corresponding confirmed attendance on the board.

## 8. Edit the layout for every display

On the updated dashboard:

1. Open **Live board**, choose **SENDAYAN**, then **Edit layout**. You can also enter **TV fullscreen** first and use **Edit layout** in its header. Entering or leaving TV fullscreen keeps your unsaved draft.
2. Enable **Use custom grid on all displays**.
3. Choose grid columns, gaps, card width/height, photo size, name size and employee sort. In fullscreen, expand **Layout settings** to change these options; collapse it to see more of the board. Save and Cancel remain available in the editor. Names and positions remain on the cards.
4. Hover over an **individual employee card** to show its handles. Drag its **right edge** for width, **bottom edge** for height, or **bottom-right corner** for both. Each card keeps its own pixel size and the surrounding cards wrap automatically. Card width is limited by its team container. Drag the card's **⠿ move handle** onto another card within the same team to reorder, or use its left/right buttons. **↺** resets that card to the default size. Focus a resize handle and use arrow keys for 10px adjustments, or Shift+arrow for 1px. Touch devices show the controls without hovering. Resizing or moving a card enables the custom grid automatically.
5. You can also drag a **department's handle** to reorder the whole group, or use its up/down buttons. Drag the group bottom-right corner to resize its column span/minimum height. Numeric Width/Min height controls also work with keyboard/touch. Group height is a minimum: groups grow to keep their employees visible.
6. Use **Show** to hide/show a group. Hidden groups remain visible in the editor. New groups appear automatically. Employee sorting operates inside each team, preserving team boundaries. Dragged card order takes precedence over the selected sort; use **Layout settings → Reset individual card sizes & order** to return to defaults. Moving a card changes its display order only; it does not change that employee's assigned team or department.
7. Press **Save for all displays**. Individual card sizes/order and the group layout are stored in the AI PC's database and connected browsers receive the update through the live event stream. Reconnecting displays fetch it again. **Cancel** discards the local preview. Concurrent saves are checked; cancel/reopen if another editor saved first.
8. Open the board on a second display on the **same server and plant** and verify the saved layout appears. No per-browser layout import is required.

Port Klang, Sendayan and the all-plants view each have their own shared layout. Selecting Sendayan does not replace Port Klang's layout. A custom layout takes precedence over the old Large photos/Compact overview modes, including TV fullscreen. To return to those modes, uncheck the custom grid option and save. The shared layout uses scrolling for content taller than the display; it does not shrink text automatically or rotate pages. On phones, the grid becomes one column; desktop/TV screens use the saved column spans. Layout settings are shared; different screen sizes can wrap content differently.

This controls the **React Live board**, including its TV display. It does not rearrange the separate Python camera touchscreen. Plant administrators can edit their own plant's layout; only the all-plants administrator can edit the all-plants view. Separate AI PC installations do not share a database and therefore do not sync layouts automatically.
