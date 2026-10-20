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
