# OpenClaw Setup Guide — OpenRouter + Telegram
### For WID3013 GeoMap Lens Demo

---

## Prerequisites
- A computer running Windows, macOS, or Linux
- Node.js v22.19+ (the installer handles this automatically)
- A Telegram account
- An OpenRouter account (free tier works for demos)

---

## Part 1 — Install OpenClaw

**On macOS / Linux / WSL2:**
```bash
curl -fsSL https://openclaw.ai/install.sh | bash
```

**On Windows (PowerShell):**
```powershell
iwr -useb https://openclaw.ai/install.ps1 | iex
```

The installer detects your OS, installs Node if needed, installs OpenClaw, and launches onboarding automatically.

**Verify the install:**
```bash
openclaw --version
openclaw doctor
```

---

## Part 2 — Set Up OpenRouter as the LLM Provider

### Step 1 — Get your OpenRouter API key
1. Go to [https://openrouter.ai/keys](https://openrouter.ai/keys)
2. Sign in or create a free account
3. Click **Create Key**, give it a name (e.g. `geomap-demo`)
4. Copy the key — it starts with `sk-or-...`

### Step 2 — Run onboarding with OpenRouter
```bash
openclaw onboard --auth-choice openrouter-api-key
```
Paste your key when prompted.

### Step 3 — Confirm the model is set
OpenClaw defaults to `openrouter/auto` after this. You can check or change it:
```bash
openclaw models set openrouter/auto
```
For demo purposes `openrouter/auto` is fine. For better vision support, consider:
```bash
openclaw models set openrouter/google/gemini-2.0-flash-001
```

---

## Part 3 — Set Up Your Telegram Bot

### Step 1 — Create a bot via BotFather
1. Open Telegram and search for **@BotFather** (verify exact handle)
2. Send `/newbot`
3. Follow prompts — choose a name (e.g. `GeoMap Lens`) and a username (e.g. `geomaplens_bot`)
4. BotFather gives you a **bot token** — looks like `123456789:ABCdefGHIjklMNOpqrSTUvwxYZ`
5. Save this token — you will need it in the next part

### Step 2 — Find your Telegram user ID
You need this to authorise yourself as the bot owner.
1. DM any bot (or your new bot)
2. Run in terminal:
```bash
openclaw logs --follow
```
3. Send a message to your bot — your numeric user ID will appear in the logs under `from.id`

Alternatively, DM **@userinfobot** on Telegram and it will reply with your user ID.

---

## Part 4 — Configure OpenClaw

### Step 1 — Open the config file
OpenClaw's config lives at `~/.openclaw/openclaw.json` (macOS/Linux) or `%APPDATA%\openclaw\openclaw.json` (Windows).

Open it in any text editor. If it does not exist yet, create it.

### Step 2 — Add OpenRouter + Telegram config
Replace the contents with (or merge into) the following:

```json5
{
  env: {
    OPENROUTER_API_KEY: "sk-or-YOUR_KEY_HERE",
  },

  agents: {
    defaults: {
      model: { primary: "openrouter/auto" },
    },
  },

  channels: {
    telegram: {
      enabled: true,
      botToken: "YOUR_BOT_TOKEN_HERE",
      dmPolicy: "allowlist",
      allowFrom: ["YOUR_NUMERIC_TELEGRAM_USER_ID"],
    },
  },
}
```

Replace:
- `sk-or-YOUR_KEY_HERE` → your OpenRouter API key
- `YOUR_BOT_TOKEN_HERE` → the token from BotFather
- `YOUR_NUMERIC_TELEGRAM_USER_ID` → your Telegram user ID (numbers only, e.g. `123456789`)

---

## Part 5 — Install Your GeoMap Lens Skill

### Step 1 — Create the skill directory
```bash
mkdir -p ~/.openclaw/workspace/skills/geomap-lens
```

### Step 2 — Copy in the SKILL.md file
Copy the `SKILL.md` file from this project into the skill directory:
```bash
cp /path/to/your/SKILL.md ~/.openclaw/workspace/skills/geomap-lens/SKILL.md
```

Or create it manually:
```bash
nano ~/.openclaw/workspace/skills/geomap-lens/SKILL.md
```
Then paste in the full SKILL.md content.

### Step 3 — Verify the skill loaded
```bash
openclaw skills list
```
You should see `geomap-lens` in the list.

---

## Part 6 — Start the Gateway and Connect Telegram

### Step 1 — Start the gateway
```bash
openclaw gateway
```
Leave this terminal running. You should see startup logs confirming OpenRouter and Telegram are connected.

### Step 2 — DM your bot on Telegram
Open Telegram and send any message to your bot (e.g. "hello").

### Step 3 — Approve the DM pairing
In a new terminal:
```bash
openclaw pairing list telegram
```
You will see a pairing request with a code. Approve it:
```bash
openclaw pairing approve telegram <CODE>
```
Note: pairing codes expire after 1 hour.

---

## Quick Reference — Key Commands

```bash
openclaw --version              # check install
openclaw doctor                 # diagnose issues
openclaw gateway                # start the gateway
openclaw gateway restart        # restart after config changes
openclaw skills list            # list loaded skills
openclaw pairing list telegram  # see pending DM pairing requests
openclaw pairing approve telegram <CODE>  # approve a pairing
openclaw logs --follow          # watch live logs
openclaw agent --message "..."  # test agent locally
```

---

## File Locations Summary

| File | Location |
|---|---|
| OpenClaw config | `~/.openclaw/openclaw.json` |
| Skill directory | `~/.openclaw/workspace/skills/geomap-lens/` |
| Skill file | `~/.openclaw/workspace/skills/geomap-lens/SKILL.md` |

---

*GeoMap Lens | WID3013 Practical CV Skill Assignment*
