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
3. **Four languages.** All customer-facing text must support Hebrew, English, Russian, and Arabic. Hebrew and Arabic are right-to-left (RTL), including any text printed in the album.
4. **Official WhatsApp only.** Use the official WhatsApp Business Platform (Meta Cloud API). Never use unofficial WhatsApp libraries (such as whatsapp-web.js or Baileys), because they risk getting the number banned.
5. **Protect customer photos.** Photos are private, often of children. Never make them public, never log them, and delete them automatically after delivery. Never send the print-quality PDF to the customer.
6. **Keep it replaceable.** Keep the album builder separate from the printing step so the printer (a local printer or Lupa) can be changed. Keep the server portable so it can move from the Mac Mini to the cloud with minimal work.
7. **Build in small stages.** Ship the simplest working version first. Manual steps are fine early on (see the roadmap in README.md).

## Planned tech stack

| Part | Choice |
|---|---|
| Messaging | WhatsApp Business Platform (Meta Cloud API). The free Meta test number during development. |
| Server | Python, running on the owner's Mac Mini at first |
| Public access | Cloudflare Tunnel (for WhatsApp webhooks) |
| Database and file storage | Supabase (free plan) |
| AI | Claude (Anthropic API): conversation in 4 languages, help choosing photos |
| Album builder | Python: photo quality checks, HTML page templates, then a print PDF and watermarked JPEG previews |
| Payment | Bit by hand at first, later Grow / PayPlus / Cardcom |

This plan is not final. If you suggest a change, explain why in simple words.

## Secrets and safety

- Never commit API keys, tokens, or passwords. Keep them in a `.env` file that is listed in `.gitignore`.
- Never commit customer photos or customer personal data.

## Current status

Stage 0 (preparation). There's no code yet. Update this section as the project moves forward.
