#!/bin/bash

# Reset Frontend Cache Script
# Use this when experiencing 404 errors or routing issues after git operations

set -e

echo "🧹 Resetting SurfSense Frontend Cache..."
echo ""

cd "$(dirname "$0")/surfsense_web"

echo "1️⃣ Stopping any running dev servers..."
pkill -f "next dev" 2>/dev/null || true
sleep 2

echo "2️⃣ Removing .next cache directory..."
rm -rf .next
echo "   ✅ .next removed"

echo "3️⃣ Removing node_modules/.cache..."
rm -rf node_modules/.cache
echo "   ✅ node_modules/.cache removed"

echo "4️⃣ Clearing npm cache..."
npm cache clean --force
echo "   ✅ npm cache cleared"

echo "5️⃣ Removing package-lock.json..."
rm -f package-lock.json
echo "   ✅ package-lock.json removed"

echo "6️⃣ Reinstalling dependencies..."
npm install
echo "   ✅ Dependencies reinstalled"

echo ""
echo "✨ Frontend cache reset complete!"
echo ""
echo "Next steps:"
echo "  1. Start the dev server: npm run dev"
echo "  2. Open browser to http://localhost:3000"
echo "  3. Clear browser cache (Ctrl+Shift+Delete) or use incognito"
echo "  4. Log in again"
echo ""
echo "If you still see 404 errors, also clear your browser's:"
echo "  • Application → Storage → Clear site data (F12 → Application)"
echo "  • localStorage"
echo "  • Service Workers"
echo ""
