# Task: Visually test the mng VS Code extension using code-server

You are testing a VS Code extension that shows mng agents in a sidebar TreeView. Your job is to install code-server, load the extension, take screenshots, and save them for retrieval.

## Step 1: Install dependencies

Run these as root/sudo:
```bash
# Install Node.js 20.x (needed for code-server and building the extension)
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

# Install playwright system dependencies for Chromium screenshots
npx playwright install-deps chromium
```

## Step 2: Install code-server

```bash
npm install -g code-server@latest
```

## Step 3: Build and package the extension

```bash
cd apps/mng-vscode
npm install
npm run build

# Package as .vsix for installation into code-server
npx @vscode/vsce package --no-dependencies --allow-missing-repository 2>/dev/null || npx vsce package --no-dependencies --allow-missing-repository 2>/dev/null
# The .vsix file will be created in the current directory
ls *.vsix
```

## Step 4: Install the extension into code-server

```bash
code-server --install-extension apps/mng-vscode/*.vsix
```

## Step 5: Configure code-server

Create a code-server config that disables authentication and opens on a specific port:
```bash
mkdir -p ~/.config/code-server
cat > ~/.config/code-server/config.yaml << 'EOF'
bind-addr: 127.0.0.1:8080
auth: none
cert: false
EOF
```

## Step 6: Create a workspace with .mng directory

The extension activates when it finds a `.mng` directory. Make sure the workspace has one:
```bash
mkdir -p /tmp/test-workspace/.mng
```

## Step 7: Start code-server in the background

```bash
code-server --disable-telemetry /tmp/test-workspace &
sleep 10  # Give it time to start
# Verify it's running
curl -s http://127.0.0.1:8080 | head -5
```

## Step 8: Install Playwright and take screenshots

```bash
pip install playwright
playwright install chromium
```

Then create and run a Python script to take screenshots:

```python
import asyncio
from playwright.async_api import async_playwright

async def take_screenshots():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1400, 'height': 900})

        # Navigate to code-server
        await page.goto('http://127.0.0.1:8080', wait_until='networkidle', timeout=60000)
        await asyncio.sleep(5)  # Let VS Code fully initialize

        # Screenshot 1: Initial state (should show the mng sidebar icon in activity bar)
        await page.screenshot(path='/tmp/test-workspace/screenshot-01-initial.png', full_page=False)

        # Try to click the mng agents icon in the activity bar
        # The activity bar items are typically in the leftmost column
        # Look for the mng agents view container
        try:
            # Try clicking the activity bar icon for mng agents
            mng_icon = page.locator('[id="workbench.view.extension.mng-agents"]')
            if await mng_icon.count() > 0:
                await mng_icon.click()
                await asyncio.sleep(3)
            else:
                # Try aria label approach
                mng_icon = page.locator('a[aria-label*="mng"]')
                if await mng_icon.count() > 0:
                    await mng_icon.click()
                    await asyncio.sleep(3)
                else:
                    # List all activity bar items for debugging
                    items = await page.locator('.action-item a').all()
                    labels = []
                    for item in items:
                        label = await item.get_attribute('aria-label')
                        if label:
                            labels.append(label)
                    print(f"Activity bar items found: {labels}")
        except Exception as e:
            print(f"Could not click mng icon: {e}")

        # Screenshot 2: After clicking mng sidebar (may show agents or welcome message)
        await page.screenshot(path='/tmp/test-workspace/screenshot-02-sidebar.png', full_page=False)

        # Screenshot 3: Full page with any error messages visible
        # Open the developer console / output panel to check for errors
        try:
            # Try keyboard shortcut to open output panel
            await page.keyboard.press('Control+Shift+U')
            await asyncio.sleep(2)
        except Exception:
            pass
        await page.screenshot(path='/tmp/test-workspace/screenshot-03-output.png', full_page=False)

        # Screenshot 4: Try to capture the status bar area
        try:
            status_bar = page.locator('.statusbar')
            if await status_bar.count() > 0:
                await status_bar.screenshot(path='/tmp/test-workspace/screenshot-04-statusbar.png')
        except Exception as e:
            print(f"Could not capture status bar: {e}")

        await browser.close()
        print("Screenshots saved to /tmp/test-workspace/")

asyncio.run(take_screenshots())
```

Save the Python script as `/tmp/take_screenshots.py` and run it:
```bash
python3 /tmp/take_screenshots.py
```

## Step 9: Copy screenshots to work directory

```bash
mkdir -p screenshots
cp /tmp/test-workspace/screenshot-*.png screenshots/
ls -la screenshots/
```

## Step 10: Summary

After completing all steps, list what screenshots were captured and describe what you see in each one. Note any issues:
- Did the extension icon appear in the activity bar?
- Did the TreeView show agents or the welcome message?
- Did the status bar show the mng item?
- Were there any errors in the output panel?

IMPORTANT: Make sure the screenshots directory is in your work directory so it can be pulled with `mng pull`.
