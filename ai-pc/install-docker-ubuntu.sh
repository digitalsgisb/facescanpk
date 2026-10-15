#!/usr/bin/env bash
set -euo pipefail
if command -v docker >/dev/null 2>&1; then
  if docker compose version >/dev/null 2>&1; then
    echo 'Docker and Compose are already installed; keeping the existing installation.'
    sudo systemctl enable --now docker
    exit 0
  fi
  echo 'Docker is installed but its Compose plugin is missing. Follow https://docs.docker.com/compose/install/linux/ for your existing Docker installation.' >&2
  exit 1
fi
source /etc/os-release
if [[ "$ID" != 'ubuntu' ]]; then
  echo 'This installer is for Ubuntu. Use the installation instructions for your OS.' >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -d -m 0755 /etc/apt/keyrings
sudo curl --fail --silent --show-error --location https://download.docker.com/linux/ubuntu/gpg --output /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
attendance_codename="${UBUNTU_CODENAME:-$VERSION_CODENAME}"
attendance_arch="$(dpkg --print-architecture)"
printf 'Types: deb\nURIs: https://download.docker.com/linux/ubuntu\nSuites: %s\nComponents: stable\nArchitectures: %s\nSigned-By: /etc/apt/keyrings/docker.asc\n' "$attendance_codename" "$attendance_arch" | sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker version
sudo docker compose version
