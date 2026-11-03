# Automatic deployment and device updates

There are two parts: deploying a pushed commit to the AI PC, and moving open browser/PWA devices to that deployed version. This update implements both mechanisms. One-time runner setup on the AI PC is required to activate automatic deployment.

## Device behavior

Each production build contains an `app-version.json` file and the same version embedded in the application. Devices check the server every 60 seconds, on reconnection and when the browser becomes visible/focused. This works on normal LAN HTTP as well as HTTPS/PWA installations.

An available update installs automatically after at least 10 seconds of inactivity, with no open dialog, unsaved form, pending write request or explicitly active editor. Inline model/lot changes, Apps Script links, executive group mapping, employee import previews and TV layout edits defer updating. A successful save releases the guard; a failed save or new input during a save keeps it blocked. The next safe idle check applies the waiting update. Network errors or a restarting server never trigger a forced reload.

Cookies and saved production/attendance records are retained. Checksheet remembers the selected production line and hash page. Attendance remembers its current page, selected board plant and TV layout mode. Native browser fullscreen may need another user gesture after a reload; TV layout is restored without requiring that gesture. Suspended/offline devices check when they resume/reconnect, subject to the browser’s background restrictions.

Every existing device needs one manual refresh/app update after this release is first deployed to install this updater. Subsequent deployed builds use the automatic flow. A GitHub push alone does not change a device until the AI PC deployment succeeds.

## One-time GitHub runner setup

Do this for **both** repositories: `digitalsgisb/smartchecksheet` and `digitalsgisb/facescanpk`.

1. On GitHub, open the repository’s **Settings → Actions → Runners → New self-hosted runner**. Select Linux x64. Follow the generated download/configuration commands on the AI PC. Use a separate runner directory for each repository; each registration token is repository-specific and temporary.
2. Register each runner with the additional label **production-digital**. The workflows require the labels `self-hosted`, `linux`, `x64`, `production-digital`.
3. Run it under the existing deployment user that owns the checkout and already has Docker access. The user must be able to fetch the repository from `origin`. Install each runner as a service using GitHub’s generated instructions, so it returns after reboot. Do not run the runner as root.
4. In each repository, open **Settings → Secrets and variables → Actions → Variables**. Create these repository variables:

   | Repository | DEPLOY_PATH | AUTO_DEPLOY_ENABLED |
   | --- | --- | --- |
   | smartchecksheet | Its existing repository directory, for example `/srv/apps/smartchecksheet` | `true` |
   | facescanpk | Its existing **repository root**, for example `/home/YOUR_USER/facescanpk` (not the ai-pc subdirectory) | `true` |

   The example paths must match the actual AI PC installation. Leave AUTO_DEPLOY_ENABLED unset until the corresponding runner is online and the path is correct. Deployment jobs skip while that variable is not `true`.
5. The deployed checkouts must be on `main` without tracked-file edits. Keep private settings in the existing `.env.docker`/`.env`, mounted runtime directories and local Compose overrides. Untracked runtime/configuration files are retained. If the app was installed only from a ZIP, first establish a Git checkout using the existing backed-up migration procedure; the workflow does not replace an arbitrary package installation.
6. On GitHub, open **Actions → Test and deploy Checksheet / Test and deploy Attendance → Run workflow**, selecting `main`, for the initial deployment. Future pushes to `main` trigger it automatically.

The GitHub-hosted verification job installs dependencies, runs the test suite and builds the frontend. Pull requests run verification only. After verification succeeds, the AI PC runner fetches the exact main-branch commit, skips a superseded push, and fast-forwards its existing checkout. It does not reset or discard local changes.

## Deployment behavior

The deployment script builds the new image while the current service remains running, then replaces only the relevant service. It automatically includes `compose.override.yaml`/`.yml` and `compose.shift-link.yaml` when present, preserving the Attendance–Checksheet network connection. It retains environment files, ports and data volumes. There is no `down -v`, database reset or image pruning.

Both repositories serialize container replacements through the deployment user’s lock file. If the new container does not pass its health check within about two minutes, the script attempts to restore the previous application image using the same volumes and configuration. This is an application-image rollback, not a database rollback. Inspect the Actions job if deployment fails.

To disable automatic deployment, set AUTO_DEPLOY_ENABLED to `false` in that repository. Device checks continue to work for manually deployed builds.

## Manual deployment remains available

From the Checksheet checkout:

```bash
git pull --ff-only origin main
bash deploy/auto-deploy.sh "$PWD" checksheet .env.docker
```

From the facescanpk repository root:

```bash
git pull --ff-only origin main
bash tools/auto-deploy.sh "$PWD/ai-pc" attendance
```

After deployment, open `/app-version.json` at each app’s normal address to confirm the version file is reachable. Keep one idle device open, deploy a later build, and verify it updates within roughly 60 seconds plus the idle/installation delay. Repeat while editing a lot/profile: it must wait until the work is saved or the form is closed. The current login and selected production line/page should survive.

Runner labels follow GitHub’s [self-hosted runner workflow rules](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job). Only trusted main-branch deployments are assigned to the AI PC runner.
