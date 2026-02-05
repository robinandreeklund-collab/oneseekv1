# Fixing 404 Error After Login

## Quick Fix (For WSL/Linux Users)

```bash
# From the repository root directory
./reset-frontend-cache.sh

# Then start the frontend
cd surfsense_web
npm run dev
```

## Manual Fix (If Script Doesn't Work)

```bash
# 1. Stop frontend dev server (Ctrl+C in the terminal running npm run dev)

# 2. Kill any lingering Next.js processes
pkill -f "next dev" || true

# 3. Navigate to frontend directory
cd surfsense_web

# 4. Delete all cache files
rm -rf .next
rm -rf node_modules/.cache  
rm -f package-lock.json

# 5. Clear npm cache
npm cache clean --force

# 6. Reinstall dependencies
npm install

# 7. Start dev server
npm run dev
```

## Browser Reset (IMPORTANT!)

After resetting the frontend, also clear your browser:

1. Open browser DevTools (Press F12)
2. Go to **Application** tab
3. Click **Storage** in left sidebar
4. Click **Clear site data** button
5. **Close ALL browser windows/tabs completely**
6. Wait 10 seconds
7. Reopen browser
8. Navigate to `http://localhost:3000`
9. Log in again

## Why This Happens

Next.js 16 with Turbopack caches compiled routes aggressively. After:
- Package updates (we upgraded multiple npm packages)
- Git operations (pulls, checkouts, reverts)
- Multiple dev server restarts

The cache becomes stale and doesn't recognize existing routes, even though they exist in the code.

## Verify It's Fixed

After the reset, in your frontend terminal you should see:

```
✓ Ready in 3.2s
○ Compiling / ...
✓ Compiled /dashboard in 1.5s
✓ Compiled /dashboard/[search_space_id]/new-chat in 2.1s
```

And in your browser, after logging in:
- You should be redirected to `/dashboard`
- Then automatically to `/dashboard/1/new-chat` (or similar)
- NO 404 error

## Still Not Working?

If you still see 404 after this complete reset:

1. **Check the route file exists**:
   ```bash
   ls -la app/dashboard/[search_space_id]/new-chat/[[...chat_id]]/page.tsx
   ```
   Should show the file exists.

2. **Verify correct ports**:
   - Frontend should be on port 3000
   - Backend should be on port 8000 (or your custom port)

3. **Try a different browser** (Chrome, Firefox, Edge)

4. **Check for Windows/WSL issues**:
   - If running backend in WSL but frontend in Windows PowerShell, this can cause issues
   - Run BOTH in WSL for best results

## Need More Help?

See the main [GETTING_STARTED.md](../GETTING_STARTED.md) guide for more detailed troubleshooting.
