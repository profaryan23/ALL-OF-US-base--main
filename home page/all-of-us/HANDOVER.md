# All Of Us — handover notes

Everything in this folder is the site's source code, ready to run anywhere.

## Stack

TanStack Start v1 (React 19 + Vite 8), Tailwind CSS v4, TypeScript.
Fonts (Playfair Display + DM Sans) load from Google Fonts via `<link>` in `src/routes/__root.tsx`.
There is no database, no login, and no backend — it is one static home page.

## Run it

```sh
npm install        # or: bun install
npm run dev        # dev server
npm run build      # production build
npm run preview    # serve the build
npm run lint       # eslint
npm run test       # vitest
```

Node 20+ (Node 22 recommended). `bun.lock` is included if you use Bun.

## Important: the photos

The five photos are hosted on Lovable's CDN. In `src/` they are imported as
`*.asset.json` pointer files (see `src/assets/`), and the `<img>` tags use the
pointer's `url`, which is a Lovable-only path:

```
/__l5e/assets-v1/<asset-id>/<filename>
```

That path does **not** exist on your own system, so the page will render with
broken images until you do one of these:

**Option A — serve locally (recommended)**
1. The original files are in `assets-original/` (also copied below):
   `campaign-duo.png`, `i.jpeg`, `l.jpeg`, `n.jpeg`, `hoodie.webp`
2. Copy them into your project's static folder, e.g. `public/photos/`.
3. In `src/routes/index.tsx`, replace each `import x from "@/assets/<name>.asset.json"`
   with a plain URL string pointing at the copied file, e.g.
   `const duo = { url: "/photos/campaign-duo.png" };`
   The five imports at the top of the file are the only places photos are used.

**Option B — keep using the CDN**
Leave the code as-is and host the site on Lovable, or proxy `/__l5e/assets-v1/`
to `https://<your-lovable-preview-host>/__l5e/assets-v1/`.

## Where things live

| Path | What it is |
| --- | --- |
| `src/routes/index.tsx` | The whole home page: top strip, header, hero, Gallery, Our Story, footer |
| `src/routes/__root.tsx` | HTML shell, Google Fonts links, page metadata |
| `src/styles.css` | Tailwind v4 theme tokens and the `glass-panel` / `photo-mono` / `fade-left` utilities |
| `src/assets/*.asset.json` | CDN pointer files for the five photos |
| `assets-original/` | The actual photo files plus `design-reference.png` (the original mock-up) |
| `src/components/ui/` | shadcn/ui primitives (mostly unused by this page) |

## Page notes (current agreed state)

- Nav: Home (`/`), Shop (`#shop`), About (`#about`), Contact (`#contact`). The
  "ALL OF US" logo also links to `/`, so logo and Home land on the same page.
- Hero: the photo fills the section; headline, tagline and description sit along
  the bottom-left, the "Find your something" button at the bottom-right.
- The hero photo is black-and-white; the Gallery and Our Story photos are full colour.
- No prices are shown anywhere — Gallery cards show a name and a short caption only.
- The Gallery section is labelled "From the photoshoot" and its four images are
  meant to be replaced with the client's own photoshoot photos.
- Delivery copy in the top strip still says "Free delivery over $75" — confirm
  or replace this before launch.
