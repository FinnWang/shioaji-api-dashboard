#!/bin/bash
# Database Reset Script
# Removes all data and recreates tables from scratch
#
# Usage: ./db/reset.sh
#
# WARNING: This will DELETE ALL DATA!

set -e

echo "=========================================="
echo "  ⚠️  DATABASE RESET SCRIPT"
echo "=========================================="
echo ""
echo "This will:"
echo "  1. Stop all services"
echo "  2. Delete PostgreSQL data volume"
echo "  3. Delete Redis data volume"
echo "  4. Restart services with fresh database"
echo ""
echo "⚠️  ALL DATA WILL BE LOST!"
echo ""
read -p "Are you sure? (type 'yes' to confirm): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "🛑 Stopping services..."
docker compose down

echo ""
echo "🗑️  Removing data volumes..."
docker volume rm shioaji-api-dashboard_postgres_data 2>/dev/null || true
docker volume rm shioaji-api-dashboard_redis_data 2>/dev/null || true

echo ""
echo "🚀 Starting services with fresh database..."
docker compose up -d

echo ""
echo "⏳ Waiting for services to be ready..."
sleep 10

echo ""
echo "✅ Database reset complete!"
echo ""
echo "Check service status:"
echo "  docker compose ps"
echo ""
echo "Check migration logs:"
echo "  docker compose logs db-migrate"
echo ""

