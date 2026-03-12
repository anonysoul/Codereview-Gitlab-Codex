#!/usr/bin/env bash
set -e

if ! command -v docker >/dev/null 2>&1; then
  echo "❌ Docker 未安装，请先安装 Docker"
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "❌ Docker Compose v2 未安装"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d

echo
echo "✅ 启动成功"
echo "👉 访问地址: http://localhost:81"
echo "👉 默认账号: admin / admin"
