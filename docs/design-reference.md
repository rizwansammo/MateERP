# MateERP design reference

Observed values from the approved **MateERP-UI** prototype (`app/globals.css`, `tailwind.config.ts`, `components/erp/MateERP.tsx`, `PageHead.tsx`, `KpiStrip.tsx`, `DataTable.tsx`, `FormPanel.tsx`, `Wordmark.tsx`). They are implemented as tokens in `frontend/src/styles/tokens.css` and as the components in `frontend/src/components/ui`.

On 2026-10-20, side-by-side screenshots of the prototype and production shells (1440×900, light, dark and compact) measured identical sidebar width, sidebar colour, header height, page background and active-item geometry.

## Colour tokens
| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#EDF0F4` | `#06090D` | Page background |
| `--sf` / `--sf2` / `--sf3` | `#FFFFFF` / `#F6F8FA` / `#EBEFF4` | `#0C1117` / `#10161E` / `#17202B` | Surfaces, table heads, hovers |
| `--sfH` | `#F4F7FA` | `#121A23` | Row / tile hover |
| `--inp` | `#FFFFFF` | `#0A0F15` | Inputs |
| `--hd` | `#FFFFFF` | `#0A0F15` | Header |
| `--bd` / `--bd2` | `#DFE4EA` / `#C9D1DB` | `#1B2430` / `#2A3542` | Borders |
| `--tx` / `--tx2` / `--tx3` | `#0D1520` / `#485365` / `#6F7A8C` | `#E4EBF3` / `#A1AEBE` / `#75839A` | Text |
| `--ac` | `#00B0F0` | `#00B0F0` | Brand cyan accent |
| `--pr` / `--prT` | `#0A78B5` / `#FFFFFF` | `#00B0F0` / `#03121C` | Primary button |
| `--lk` | `#0A6EA6` | `#4FC6F3` | Links |
| `--ok` / `--okS` | `#0E7A4E` / `#E2F3EA` | `#3FD18C` / 12% | Success |
| `--warn` / `--warnS` | `#9A5B00` / `#FCF0DA` | `#F2B34A` / 12% | Warning |
| `--err` / `--errS` | `#BF2A30` / `#FBE6E6` | `#FF6B6B` / 12% | Error |
| `--info` / `--infoS` | `#0A6EA6` / `#E1F1FA` | `#4FC6F3` / 13% cyan | Info |
| `--neu` / `--neuS` | `#5A6577` / `#ECEFF3` | `#94A2B4` / 12% | Neutral |
| `--c1…c6` | `#00B0F0 #0B2A4A #9AA6B8 #1F9D6B #E39B2D #C2454B` | c2 `#3F74A8`, c3 `#5E6C80` | Chart series |
| `--sb` | `#0A0F16` | `#080C11` | Sidebar (dark in both themes) |
| `--sbBd` / `--sbH` | `#18212C` / `#121A24` | `#161E28` / `#101721` | Sidebar border / hover |
| `--sbTx` / `--sbTx2` | `#C3CDD9` / `#7A889B` | same | Sidebar text |
| `--sbA` | `rgba(0,176,240,.13)` | same | Active nav item |
| Sidebar extras | group label `#556275`, company card `#0E141C`, footer note `#4E5B6D` | same | |
| Splash | bg `#06090D`, text `#F4F7FA` | same | Boot screen |

## Typography
- **Interface:** IBM Plex Sans 400/500/600/700, base 13px. **Figures and references:** IBM Plex Mono. Icons: **Material Symbols Sharp**.
- **Wordmark:** Astro (`frontend/src/assets/fonts/astro.ttf`).
- **Scale:**
  - Page title 24px/600, `-.015em`, line-height 1.15.
  - Drawer title 19px/600.
  - Panel title 13.5px/600.
  - Body 13px.
  - Secondary text 12–12.5px.
  - Labels 10.5px/600, uppercase, `.07–.1em` tracking.
  - Sidebar group label 10px/600, `.14em` tracking.
- Prototype controls use `font:` shorthand, so their line-height is `normal`. Production shell controls use `leading-[normal]` to match.

## Geometry
- **Sharp corners everywhere** (radius 0). Borders are 1px solid.
- **Sidebar:**
  - Width 264px, compact 64px. Width transition `.18s`; transform `.2s` for the off-canvas drawer.
  - Brand row 60px, padding 0 18px, wordmark 23px. Compact mark: "M" 24px + "ERP" 10px cyan.
  - Company card: margin 12/12/4, padding 10/12, 30px avatar.
  - Group label: padding 14/20/6.
  - Item: 36px tall, padding 0 18px, gap 11px, icon 19px. Active: sbA background, white 600 text, cyan icon, 2px cyan bar inset 6px top and bottom.
  - Sub-menu: 1px rail at left 29px. Sub-item 30px tall, 12.5px, padding 0 12 0 16. Active sub-item: cyan rail segment, white 600 text.
  - Footer: padding 10/12, 30px collapse button.
- **Header:**
  - 56px tall, padding 0 18px, gap 12px.
  - Controls are 34px. Search is 340px at ≥1180px, otherwise 34px.
  - Breadcrumbs: 12.5px, 15px chevrons, last crumb 600 in `--tx`.
- **Page:** padding 24 28 56, max width 1640px, section gap 18px. Eyebrow has a 14×2px cyan rule.
- **Panels:** `--sf` with a 1px `--bd` border. Panel header padding 12/14.
- **KPI strip:** shared-border grid with tiles of minimum 190px. Tile padding 16/18/15, value 22px/600, 2px tone bar on top.
- **Tables:**
  - Head: `--sf2`, cells 9/12, 10.5px/600 uppercase, `.07em` tracking.
  - Rows: cells 10/12 (dense 7/12), `--bd` bottom border, `--sfH` hover. Money is right-aligned with tabular numbers.
- **Buttons:** 34px tall, padding 0 14px, 12.5px. Primary/secondary/danger/ghost variants. Small size is 30px, padding 0 11px, 12px. Hover `brightness(1.08)`.
- **Inputs:** 34px tall, padding 0 10px, 13px, `--inp` background, `--bd` border, `--ac` on focus.
- **Badges:** 20px tall, padding 0 7px, 10.5px/600 uppercase with a 5px square dot.
- **Overlays:** drawer scrim `rgba(3,7,12,.58)`, mobile nav scrim `.5`. Menus use the `rise .12s` animation and a `0 18px 50px rgba(0,0,0,.18)` shadow.
- **Focus:** 2px `--ac` outline with 1px offset.

## Motion
- `load` 1.1s (splash progress bar)
- `rise` .12–.15s (menus, toasts)
- `spin` 1s (spinners)

## Splash
Full-screen `#06090D`, 22px gap between:
- 64px wordmark
- "ENTERPRISE RESOURCE PLANNING" in 11px at `.42em` tracking, `#7A889B`
- 220×2px track `#18212C` with a 30% cyan bar
- Footer note in 11px `#4E5B6D`

## Breakpoints
| Width | Behaviour |
|---|---|
| < 640px | Only the current breadcrumb shows; search is hidden |
| < 1000px | Sidebar becomes an off-canvas drawer with a scrim and a header menu button |
| ≥ 1000px | Sidebar is inline and can collapse to 64px |
| ≥ 1180px | Header shows the full search field, "New" label and account name |

## Wordmark
Reference: `docs/design/mateerp-wordmark-reference.png`.
- "M" at 1em
- "ATE" at .667em with .07em left margin and .035em tracking
- "ERP" at 1em in `#00B0F0` with .035em left margin and .02em tracking
- Baseline-aligned, line-height 1

## Phase 2 components
Values below come from the prototype's `FormPanel.tsx`, `DataTable.tsx`, `Settings.tsx`, `MateERP.tsx` and `DocViewer.tsx`.

| Component | Specification |
|---|---|
| Drawer (`Overlay.tsx`) | Right-hand panel, default width 640px (560 or 520 for small forms). Background `--sf`, left border `--bd2`, shadow `-24px 0 60px rgba(0,0,0,.28)`. Scrim `rgba(3,7,12,.58)`. Header padding 20/24/16: eyebrow 10.5px/600 cyan at `.09em`; title 19px/600; 32px close button. Body padding 20/24/24 on a 12-column grid with 16×14px gaps. Footer `--sf2` with padding 14/24 and 34px buttons |
| Modal / ConfirmDialog | Centred at 12vh; 460px wide; `--bd2` border; shadow `0 30px 80px rgba(0,0,0,.35)`; same header and footer anatomy as the drawer |
| Toast | Bottom-right; 280–440px; padding 11/14; `--tipBg`/`--tipFg`; 3px tone left edge; 18px icon; `rise` animation |
| InfoPanel | Auto-fit grid `minmax(min(100%,300px),1fr)` with 18px gap. Header 12/16 at 13px/600. Rows 7px with `--bd` divider at 12.5px; label `--tx3`, value right-aligned |
| Banner | Padding 11/14 (compact 9/12); tone soft background with a 1px tone border; 18px tone icon; 12.5px/1.5 |
| Table toolbar | Padding 12/14 with a `--bd` bottom border. Title 13.5px/600, subtitle 12px `--tx3`. Filter chips: 30px segments in a `--bd2` frame, active `--tx`/`--sf`. Search: 220×30px |
| Row actions | 26px tall, padding 0 8px, 11.5px/500, `--bd2` border, no wrap, 4px gap |
| Pager | Padding 8/14 at 12px `--tx3`; 28px square previous/next buttons |
| Segmented control | 32px segments (30px small) in a `--bd2` frame; active `--tx` background, `--sf` text |
| Checkbox | 16px box; checked `--pr` fill with a check icon; label 13px/1.45; hint 11.5px with a 26px indent |
| Toggle (modules) | 30px On/Off button with `toggle_on`/`toggle_off` icon; On uses the primary style |
| Restricted card | 560px; padding 32px; 30px lock icon in `--warn`; title 18px/600; body 13px `--tx2` |
| Account menu | 290px dropdown 40px below the button. Header shows name 13.5px/600, email 12px and a role pill (`--infoS`/`--info`, 10.5px uppercase). 12.5px items with 17px icons |
| Notifications | 410px fixed panel at top 62px / right 12px; rows padding 11/14; unread dot 7px `--ac`; 18px `--err` count badge |
| Document viewer / branding studio | `#0A0E13` background; 54px toolbar in `#0D131B` with a `#1D2733` divider; controls 30px with `#2A3644` borders; zoom steps 50–125% |

## Authentication screens
The prototype has no sign-in screen, so it extends the approved splash composition.
- **Brand panel:** 44% wide (max 620px), `#06090D` background with a faint 64px `--sbBd` grid. Tagline 11px at `.42em`; wordmark 56px; 220×2px track with a 30% cyan bar; "A NetaMate product" 11px.
- **Form card:** 400px, `--sf`, 1px `--bd`, padding 32px. Eyebrow with a 14×2px cyan rule; 24px/600 title. Fields and buttons use the standard 34px controls.
- **Mobile:** below 768px the brand panel collapses to a top band.

## Invoice and receipt templates
Reproduced from `components/erp/FinDoc.tsx` in `frontend/src/features/documents/`.
- **Size and type:** A4 at 96 dpi (794×1123px). Body 11.5px/1.45; text `#111827`, secondary text `#4B5563`/`#6B7280`.
- **Spacing:** compact 30/12/5px, regular 42/18/8px, airy 54/24/11px (page padding / section gap / row padding).
- **Meridian:** 7px brand band with a 180px accent segment; "INVOICE" 30px/700 at `.14em` in the brand colour.
- **Ledger:** 2px `#111827` rule under the header; "Tax Invoice" 11px at `.3em`; number 20px in the accent colour. Transparent table head with a 1.5px rule; Total Due row with a 2px top rule.
- **Atlas:** 220px brand-colour sidebar with company details and meta; "Invoice" 34px/700.
- **Table styles:** lined (`#E5E7EB` rows), striped (`rgba(17,24,39,.035)`), boxed (`#D1D5DB` frame, `#F3F4F6` head). Columns: `28px · 1fr · 54px · 92px · 50px · 54px · 100px`.
- **Totals:** 270px column; Total Due bar padding 10/12. Figures follow Settings → Currency (symbol or code, lakh or international grouping); line figures show no symbol.
- **Receipts (794×600px):**
  - Official: 2px brand frame plus 1px accent outline inset 7px; "OFFICIAL MONEY RECEIPT" 17px at `.32em`.
  - Compact: 3px brand rule under the header.
  - Shared: amount block on the brand colour (22px/700), amount in words (lakh/crore for BDT), seal 112px rotated −9° at 86% opacity, signature block 190px.
- **Seal (stamp editor):** 360-unit SVG.
  - Circle: rings at r168 (7px stroke), r150 and r92 (2px); arc text 25px/700 at r121; ★ at ±121; centre 40px (30px when longer than 6 characters).
  - Square: frames at 328 and 300; text 22px/700; centre 50px/800.
- **Typed signature:** Herr Von Muellerhoff 36px (34px on receipts) in `#1F2A44`.
- **Previews:** watermarked PREVIEW, rotated −28° (receipts −20°), and use clearly fictional sample data.
