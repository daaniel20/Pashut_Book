# CLAUDE.md

Guidance for Claude (and other AI assistants) working on this project. Read README.md for the full product description.

## About the owner

- The owner is **building this alone, with AI help**, and is **not a software developer**.
- **Explain things in simple, plain language.** Avoid jargon. When a technical term is needed, explain it in one short sentence.
- Keep answers short unless the owner asks for detail. Give a clear recommendation rather than a long list of options.
- The owner is learning. When you add something new (a tool, a file, a command), briefly say what it is and why it's needed.

## About the project

Pashut Book is a WhatsApp bot that turns customers' photos into a **printed photo book**. It's for non-tech-savvy customers in Israel (young parents and grandparents).

The parts of the product decided so far:
- Customers send photos in WhatsApp (HD option), up to 50–100 photos.
- They choose one of **2 designs**.
- The album is designed **fully automatically**.
- Customers see **small, watermarked preview images only, never the PDF**.
- They can ask for a **limited** number of simple changes.
- They pay with Bit or a credit card link.
- **The owner approves every album before printing.**

## Guiding principles

1. **Low cost first.** Prefer free tiers and things the owner already has (the Mac Mini). Don't add paid services unless there's a real need, and say what they cost before suggesting them.
2. **Simple for the customer.** Every customer-facing message should be short and clear, with buttons wherever possible. Assume the customer is a grandparent.
3. **Hebrew first, more languages later.** Launch in Hebrew only. Russian, Arabic and English come later, each with its own marketing campaign. Write code so new languages are easy to add later (keep customer-facing text separate from the code, not hard-coded). Hebrew and Arabic are right-to-left (RTL), including any text printed in the album.
4. **Official WhatsApp only.** Use the official WhatsApp Business Platform (Meta Cloud API). Never use unofficial WhatsApp libraries (such as whatsapp-web.js or Baileys), because they risk getting the number banned.
5. **Protect customer photos.** Photos are private, often of children. Never make them public, never log them, and delete them automatically after delivery. Never send the print-quality PDF to the customer.
6. **Keep it replaceable.** Keep the album builder separate from the printing step so the printer (a local printer or Lupa) can be changed. Keep the server portable so it can move from the Mac Mini to the cloud with minimal work.
7. **Build in small stages.** Ship the simplest working version first. Manual steps are fine early on.
8. **Sales must not wait for the bot.** The project runs two tracks in parallel: a **build track** (the bot) and a **sales track** (real paying customers, with albums made by hand if the bot isn't ready). Stage 4 starts only after the go/stop decision passes. See README.md and ROADMAP.md.
9. **Our advantage is marketing, service and speed, not the tool.** Don't over-polish technology the customer doesn't see.

## Planned tech stack

| Part | Choice |
|---|---|
| Messaging | WhatsApp Business Platform (Meta Cloud API). The free Meta test number during development (it can message only up to 5 pre-registered numbers), then a real business number. |
| Server | Python, running on the owner's Mac Mini at first |
| Public access | Cloudflare Tunnel (for WhatsApp webhooks) |
| Database and file storage | Supabase (free plan) |
| AI | Claude (Anthropic API): understanding customers' free-text messages (Hebrew first), help choosing photos |
| Album builder | Python: photo quality checks, HTML page templates, then a print PDF and watermarked JPEG previews |
| Payment | Bit by hand at first, later Grow / PayPlus / Cardcom |

This plan is not final. If you suggest a change, explain why in simple words.

## Secrets and safety

- Never commit API keys, tokens, or passwords. Keep them in a `.env` file that is listed in `.gitignore`.
- Never commit customer photos or customer personal data.

## Current status

Planning. The ROI calculator is a [Google Sheet](https://docs.google.com/spreadsheets/d/1ZCKRQZeCI5KIRq7gG5fmPfoNe2K_A7gINmlTygY1NUw/edit) in the owner's Google Drive (private). It is the live source for price and cost assumptions. The build track (Stage 0) and the sales track (weeks 1–2) start together. The fixed date for the first paying strangers is not set yet. Task 0.1 ✅: development and testing use the app "Pashut Album Test" under the owner's older "headyhelmet" portfolio, because Meta blocks sending from new unverified portfolios. Use it only for the owner's and family phones, never customers. The real "Pashut Book" portfolio (app "Pashut Album"; Meta bans "Book" in app names) must pass Business Verification and become the home of the bot before customers (task 0.4). The WhatsApp IDs and tokens go in `.env` on the Mac, not in the repo. Guide: `docs/setup/0.1-meta-whatsapp.md`. Task 0.2 ✅ (Nov 20, 2026): the Mac Mini (Apple Silicon, macOS, FileVault on, Homebrew Python 3.15) never sleeps and restarts after a power cut, but after a power cut someone must type the password (FileVault) before anything runs. Cloudflare Tunnel "mac-mini" (Zero Trust Free plan, runs at boot as a LaunchDaemon) serves https://hello.pashutbook.com → http://localhost:8000. Guide: `docs/setup/0.2-mac-mini-tunnel.md`. The test page is `server/hello.py`, started at boot by `deploy/mac/install-hello-service.sh` (a LaunchDaemon). The project lives in `~/pashut-book` on the Mac (not Documents: macOS blocks background programs there). Domain **pashutbook.com** bought on Cloudflare (Nov 2026, ~$11/year, auto-renew). It will also serve email (Cloudflare Email Routing) and a landing page, both needed for Meta verification (task 0.4). Tailscale Funnel was considered and rejected: its free plan is for non-commercial use only. Business registration (עוסק פטור) is not done yet. It's needed for Meta Business Verification (task 0.4) and for taking payments. Ad strategy will be planned from scratch in a separate session. Task 0.3 ✅ (Nov 21, 2026): Supabase project `pashut-book` created (free plan, org "daaniel20's Org", region Frankfurt eu-central-1, URL https://jyfnxrktbpgklihastvc.supabase.co). The bot uses only `SUPABASE_URL` and `SUPABASE_SECRET_KEY` (an `sb_secret_` key, in `.env` on the Mac). Check with `server/check_supabase.py`. Guide: `docs/setup/0.3-supabase.md`. Both are saved in `.env` on the Mac and the connection works. Tables and a private photo bucket come in task 1.3. **Next build task: 1.1** (first bot).

Update this section as the project moves forward.
