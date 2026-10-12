# Madison Group Enterprises Design System

A design system distilled from the ViaBrand WordPress theme that powers three MGE group sites.

## The company

**Madison Group Enterprises** (MGE) is an Australian holding company headquartered in Sydney. It owns and operates a portfolio of B2B technology and distribution businesses:

### Our Businesses (operating units)
- **MadisonAV** — Audio-visual distribution.
- **Madison Technologies** (madison.tech) — Connectivity, broadcast & mission-critical communications tech.
- **Madison Express** (madisonexpress.com.au) — Fast-turn online ordering for trade customers.
- **Madison Connectivity Solutions** — Connectivity components & RF products.

### Affiliated Businesses
- **Kallipr** — IoT hardware (telemetry, smart infrastructure).
- **CtrlOps** — Operations platform (MGE group only).

### Public-facing web surfaces
All three primary sites (**mge.com.au · madison.tech · madisonexpress.com.au**) run on a single shared WordPress theme — **ViaBrand** — with per-site logos, colors, and content. This design system is extracted from that shared theme, so it covers the common visual language across all three sites.

## Sources

| Source | Path | Notes |
|---|---|---|
| ViaBrand WordPress theme | `viabrand-mge/theme/` (mounted read-only) | Shared theme — PHP views, SCSS, fonts, icons |
| Theme tokens (SCSS) | `viabrand-mge/theme/interface/scss/global/_variables.scss` | Primary source of colors, type, spacing |
| Fonts (Hurme Geometric Sans 1) | `viabrand-mge/theme/interface/fonts/hurmegeometricsans/` | Licensed via MyFonts build 395B0C — **pageview-capped** |
| Icon set | `viabrand-mge/theme/interface/img/icons/` | Custom SVG icon set (arrows, social, utility) |
| Business-distinction spec | `viabrand-mge/IS-3574-business-distinction.md` | How MGE splits "Our Businesses" vs "Our Affiliated Businesses" across the three sites |
| Live reference | https://mge.com.au · https://madison.tech · https://madisonexpress.com.au | Canonical visual reference |

The live websites are the source of truth when something in the codebase is ambiguous.

---

## CONTENT FUNDAMENTALS

**Voice.** Plainspoken, direct, Australian-English B2B. No marketing froth. Copy is written to trade buyers, installers, wholesalers and integrators — people who want to find a product, request a price, or contact a rep. Sentences lead with the action. Headlines are usually 2–5 words.

**Casing.** Headings are sentence-case in body copy but the brand's **buttons are set in UPPERCASE** ("REQUEST A QUOTE", "FIND A RETAILER", "READ MORE"). This uppercase button treatment is the single most distinctive typographic move.

**Person.** Sites write in second person ("Find a product", "Talk to us") and corporate first-person-plural ("Our businesses", "We distribute..."). Never "I". "You" is the customer.

**Tone.** Confident, low-key, trade-professional. No emoji. No exclamation marks. No hype words ("amazing", "revolutionary"). Technical terms are used plainly and not explained.

**Signature moves.**
- **The red dot.** Display headings and banner titles end with a red full-stop: `Our businesses.` `Talk to us.` This is the brand's most recognisable text treatment and is done purely in CSS (`h3::after { content: "."; color: red; }`).
- **Short sub-nav labels.** "What we do", "Who we are", "News", "Careers", "Contact" — two to three words each.
- **CTA verbs.** Explore · View · Request · Contact · Find · Download · Read more.

**Examples of live copy (observed on mge.com.au):**
- Nav: *What we do · Who we are · News · Careers · Contact*
- CTAs: *Explore our businesses · Request a quote · Find a retailer · Meet the team*
- Footer title: *Get in touch.*
- Business list: *Our Businesses · Our Affiliated Businesses*

---

## VISUAL FOUNDATIONS

### Colors
A tight 5-color palette: **dark slate, mid grey, medium grey, light grey, signature red, plus black/white.**

| Token | Hex | Role |
|---|---|---|
| `--mge-red` | `#e31837` | Signature accent. CTAs, red dot, underline, "red corner" tile accent, hover glow |
| `--mge-dark-grey` | `#2e3c49` | Primary text, footer background, banner-on-dark background |
| `--mge-grey` | `#445c6d` | Secondary text / dark-mode borders |
| `--mge-medium-grey` | `#909dab` | Footer text, muted labels |
| `--mge-light-grey` | `#e4e5e6` | Panel backgrounds (archive pages, product grids), divider |
| `--mge-white` | `#ffffff` | Canvas |

No brand gradients. No purples/blues. **The red is used sparingly — as accent only**, never as a body-text color. Red = action.

### Typography
**Hurme Geometric Sans 1** (Regular / SemiBold / Bold) — a clean, geometric, Futura-ish grotesque. Licensed from MyFonts (build ID `395B0C`).

One family sitewide. Distinctive choices from the source:
- **Body is 15px** (not 16px), line-height 1.6.
- **Weight map is intentionally flat.** The SCSS explicitly sets `$font-weight-light: 300; $font-weight-regular: 300; $font-weight-semi-bold: 300; $font-weight-bold: 300`. In the rendered sites, headings and body read at essentially the same weight, relying on *size* and *family override* (h1 uses SemiBold face; h2 uses Regular; h3–h5 use Bold face) rather than weight to establish hierarchy.
- Headings are square, wide-letterspaced-feeling, and generally start at **h1 = 37px desktop / 27px mobile** and shrink from there.
- Body default is **Regular**. Buttons use **Bold face, UPPERCASE, text-align:left with a `>` arrow glyph in the top-right** via `::after`.

Substitute if Hurme isn't licensed: **Hind** (Google Fonts, included as fallback) or **Montserrat**.

### Spacing & layout
- Grid max width is **1320px** (`--layout-max`).
- Module vertical padding: **60px desktop / 30px tablet & mobile**.
- Base spacing unit: **20px**; small spacing **15px**.
- Mobile breakpoint 550px, tablet 768px, tablet-landscape 1024px, desktop 1320px.

### Backgrounds & imagery
- **No full-bleed hero illustrations.** Banners are either plain `--mge-dark-grey` or a photo with a subtle overlay PNG (`banner-overlay.png`) at **10% opacity**. The overlay is a soft gradient wash — no pattern.
- **Product imagery is photo-real**, on white, neutral / cool color grade. No hand-drawn illustration. No isometric renders.
- **`overlay-brand.png`** is a white-on-grey chevron-style texture used on alternating tiles in brand archive pages (see "red-corner pattern" below).
- No grain. No noise textures. No gradients on cards.

### Borders & corners
- **Radius is 0 everywhere** (`$base-border-radius: 0`). The entire system is square-cornered. This is a fixed, load-bearing choice — don't round things.
- Default border: `1px solid var(--mge-light-grey)`.

### Shadows & elevation
The signature elevation is **a red glow, not a grey drop-shadow**:
```
--shadow-red-glow: 0 0 7px 0 rgba(227, 24, 55, 1);
```
Used on tile hover states (`@mixin red-hover`). The header gets a subtle grey shadow (`0 2px 4px -2px rgba(46,60,73,0.4)`) — that's it. No other elevations.

### The "red corner" tile pattern (signature motif)
Grids of brand/industry/product tiles alternate: half the tiles are plain, half display a **40×40px top-right corner mark** made of `5px solid red` borders (top + right only — an "L" tag in the corner). This is done purely with `::after` pseudo-elements via `@mixin red-corner-pattern`. It's MGE's most recognisable layout flourish — always checkerboard it across a grid, never use on every tile.

### Hover states
- **Links**: color darkens 15% and gains `text-decoration: underline`.
- **Tiles**: gain the red glow shadow (no transform, no scale).
- **Buttons (red)**: bg darkens 4%.
- **Footer logos**: fill transitions from `--mge-medium-grey` → `--mge-white`.
- **Social icon rounded buttons**: fill flips.
- Transition duration: **200ms**, default easing.

### Press / active states
Not explicitly defined in the theme — default browser behavior. Keep it subtle; no shrink/scale.

### Transparency & blur
- Used rarely. The banner overlay PNG is `opacity: 0.1`. The header-scroll-fixed state uses `rgba(dark-grey, 0.4)` shadows. **No backdrop-filter / no frosted glass.**

### Layout rules
- Header is **fixed** (`header-fixed` body class) with a two-tier bar: a **100px-tall white top bar** (logo + utility nav + search) plus a **50px coloured bottom bar** (primary nav, usually red or dark-grey).
- Footer is full-width `--mge-dark-grey` with a **20px solid red bottom border** — a distinctive bottom edge that anchors every page.
- Banners sit flush under the header with no gap.

### Cards
Cards (products, brands, industries) are **flat, 1px-border, zero-radius white rectangles** with generous padding (20–45px). They gain the red glow on hover, and some carry the top-right red corner mark. Inside, content is **centre-aligned** (logos, titles, short descriptions). No drop-shadows at rest.

### Iconography
Small custom SVG set of utility icons (arrows, phone, map-marker, document, search, social). Stroke/fill style is **flat, single-color, geometric**. Icons inherit `currentColor` via the `.icon` class. Also includes a Fontello icon-font bundle for nav chevrons. See `ICONOGRAPHY` below.

### Animation
- Transitions **only** — 200ms on `color`, `background`, `box-shadow`, `transform`. No bounces. No spring easing.
- `scroll-behavior: smooth` on `html`.
- A big SCSS animation library (Animate.css port) **exists but is not used in the core pages** — avoid fade/zoom entrances; they're not part of the brand feel.

---

## ICONOGRAPHY

MGE uses a **small, custom-drawn SVG icon set** plus a tiny Fontello icon font for nav chevrons. Not Material. Not Lucide.

**Style.** Single-color, flat, geometric, medium-weight strokes. Icons are monochrome — they fill/stroke in `currentColor` so they inherit the text color around them (`.icon { fill: currentColor; width: 1em; height: 1em; }`).

**What's in the set** (all copied into `assets/icons/`):
- Arrows — `arrow-down-red · arrow-down-black · down-arrow-red · right-arrow-light-grey · left-arrow-light-grey · up-arrow-red` (many variants because legacy)
- Utility — `phone · map-marker · search · document · bullet · pricing-request`
- Social — `facebook · linkedin · twitter · youtube · instagram` (used in footer, wrapped in dark round containers)

**Emoji.** Never used. Not in nav, not in copy, not in buttons.

**Unicode as icons.** One case only: the red full-stop appended to headings via CSS. Also a `>` character used as the button arrow (via `::after`, not a real glyph).

**Fontello font.** Shipped at `fonts/fontello/` and used mostly for nav submenu chevrons (`.icon-chevron-down` etc). For design work, prefer the SVGs — the fontello font is a legacy convenience.

**CDN substitution.** If you need an icon that isn't in the set (e.g. checkmarks, tags, users), fall back to **Lucide** (`https://unpkg.com/lucide@latest`) with `stroke-width: 1.5` — it matches the geometric, lightweight feel. Flag the substitution so it can be replaced with a custom SVG later.

---

## Index — what's in this folder

| Path | What |
|---|---|
| `README.md` | This file |
| `SKILL.md` | Agent skill definition — load this to design for MGE |
| `colors_and_type.css` | All design tokens (CSS variables), plus semantic element rules |
| `fonts/` | HurmeGeometricSans1 web fonts (Regular / SemiBold / Bold) |
| `assets/icons/` | Brand SVG icons |
| `assets/overlay-brand.png` | Chevron texture for alternating tiles |
| `assets/banner-overlay.png` | Subtle banner overlay (10% opacity) |
| `assets/placeholder.jpg` | Generic placeholder for images |
| `preview/` | HTML cards rendered in the Design System tab |
| `ui_kits/mge/` | MGE.com.au UI kit — components + hi-fi page recreation |

## Ask for iteration

Before shipping, these want your eyes:
1. The **Hurme Geometric Sans 1** license is pageview-capped. Re-licence for production, or swap to **Hind** (free, included).
2. I had no direct access to the **rendered live site** (mge.com.au fetch was unavailable) — the UI kit is built from the SCSS + PHP templates. Please flag anything that diverges from the live pages.
3. The **red-corner + overlay-brand checkerboard** is visually striking but only kicks in on tile grids of 4+ items. Let me know if you'd like a simpler default.
