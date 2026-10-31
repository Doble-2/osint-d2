#!/bin/sh
# Installs the OSINT-D2 dashboard with Docker, without cloning the repository.
# Creates ./osint-d2 with the Compose file, a .env, and a reports folder.
set -eu

BASE_URL="https://raw.githubusercontent.com/Doble-2/osint-d2/main"
DIR="${1:-osint-d2}"

command -v docker >/dev/null 2>&1 || { echo "Docker is required: https://docs.docker.com/get-docker/" >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 is required." >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "curl is required." >&2; exit 1; }

mkdir -p "$DIR/reports"
cd "$DIR"

curl -fsSL "$BASE_URL/docker-compose.yml" -o docker-compose.yml
# An existing .env holds your keys: never replace it.
if [ ! -f .env ]; then
  curl -fsSL "$BASE_URL/.env.example" -o .env
  chmod 600 .env
fi

# The container runs as UID 1000 and has to write reports here.
if [ "$(uname -s)" = "Linux" ] && [ "$(id -u)" != "1000" ]; then
  echo "Warning: reports may fail to save, because the container runs as UID 1000. To fix it, run:" >&2
  echo "  sudo chown 1000:1000 $(pwd)/reports" >&2
fi

docker compose up -d

echo
echo "OSINT-D2 is running at http://localhost:8000"
echo "Add your AI key to $(pwd)/.env, then run: docker compose up -d"
