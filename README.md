# 🌿 Mes Plantes

A small web app to take care of your houseplants. Snap a photo, and an AI will identify the plant and write a care guide (light, watering, temperature, etc.). You can also log waterings, ask questions, and get health check-ups from photos.

The app interface is in **French**.

---

## What you need before starting

You'll need three things. Don't worry — you only set them up once.

### 1. A computer (Mac, Windows, or Linux)

These instructions are written for a Mac. On Windows or Linux the steps are very similar.

### 2. Python (the language the app is written in)

Open the **Terminal** app (on Mac: press `Cmd + Space`, type "Terminal", press Enter).

Type this and press Enter:

```
python3 --version
```

If you see something like `Python 3.10.x` or higher, you're good. If you see "command not found", install Python from https://www.python.org/downloads/ — pick the big yellow "Download Python" button and run the installer.

### 3. An Anthropic API key (for the AI)

The app uses Claude (Anthropic's AI) to identify plants. You need a personal key.

1. Go to https://console.anthropic.com/
2. Create an account
3. Click **API Keys** in the menu, then **Create Key**
4. Copy the key that starts with `sk-ant-...` and keep it somewhere safe — you'll paste it in step 4 below

> 💡 Anthropic gives you some free credits to start. After that, identifying a plant costs a few cents.

---

## Installing the app (one time only)

Open the Terminal and copy-paste each block, one at a time. Press Enter after each.

### 1. Download the app

```
cd ~/Documents
git clone https://github.com/capmann/plantes.git
cd plantes
```

> If you get "command not found: git", install Git from https://git-scm.com/download/mac and try again.

### 2. Create a private space for the app's tools

```
python3 -m venv .venv
source .venv/bin/activate
```

After this, you should see `(.venv)` at the start of your Terminal line. That means it worked.

### 3. Install what the app needs

```
pip install -r requirements.txt
```

Wait until it finishes (it can take a minute).

### 4. Save your Anthropic API key

```
echo "ANTHROPIC_API_KEY=sk-ant-paste-your-key-here" > .env
```

⚠️ Replace `sk-ant-paste-your-key-here` with the real key from step 3 of "What you need". Keep the quotes.

---

## Using the app

Every time you want to use the app:

### 1. Open the Terminal and go to the app folder

```
cd ~/Documents/plantes
source .venv/bin/activate
```

### 2. Start the app

```
python3 app.py
```

You'll see a message like:

```
Mes Plantes est accessible sur :
  - http://localhost:5000
  - http://192.168.1.x:5000  (depuis ton telephone)
```

### 3. Open it in your browser

- **On your computer:** open http://localhost:5000
- **On your phone** (must be on the same Wi-Fi): open the second address (the one with `192.168...`)

### 4. Stop the app

When you're done, go back to the Terminal and press `Ctrl + C`.

---

## What the app can do

- 📸 **Add a plant** — take a photo, the AI identifies it and generates a complete care guide
- 💧 **Track waterings** — log when you water each plant
- 🪴 **Track repottings** — note when you repot
- 🩺 **Health check-ups** — upload a new photo and the AI tells you how the plant is doing
- 💬 **Ask questions** — chat about a specific plant ("why are the leaves yellow?")

---

## Common problems

**"command not found: python3"** → Install Python (see step 2 of "What you need").

**"command not found: git"** → Install Git from https://git-scm.com/download/mac.

**The app starts but says "ANTHROPIC_API_KEY"-related errors** → Your `.env` file is missing or the key is wrong. Redo step 4 of installation.

**Port 5000 already in use** → Another app is using that port. Close other apps or restart your computer.

**My phone can't open the second address** → Your phone and computer must be on the same Wi-Fi network.

---

## Privacy

Everything stays on your computer — your photos, your plant list, your watering history. The only thing sent online is the photo you upload (sent to Anthropic so the AI can analyze it).
