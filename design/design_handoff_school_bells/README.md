# Handoff: School Bells – main control page

## Overview
This is the main operator page for the `school_bells` MUSE Python program (repo `jmmadisonav/muse_school_bells`). It shows the next scheduled bell with a live countdown and lets staff ring a bell manually or hold scheduled bells. It also lists today's schedule and shows the bell tone and USB audio adapter status. The tone values come from `main.py`: 1000 Hz, 3 s, level 0.25 (about −12 dBFS), on the Unitek Y-247A adapter (VID `0x0D8C`, PID `0x0014`).

## About the design files
`School Bells.dc.html` is a **design reference built in HTML**. It's a prototype that shows the intended look and behaviour, not production code to copy. Recreate it in whatever environment the project uses to serve its UI. The repo has no web UI yet, so pick the most suitable approach for a MUSE controller, for example a small web page served by the program or the controller's own UI layer. Then wire it to the existing playback code.

To open the reference, keep the `_ds/` folder next to the `.dc.html` file and open the file in a browser.

## Fidelity
**High fidelity.** Colours, type, spacing and the MGE brand treatments are final. Bell times, the last-playback text and the adapter format/endpoint values are **placeholders** that should come from real data.

## Screen: Today (main page)
The page is a vertical stack: header, hero, a panel grid on a grey background, then the footer. Content max width is 1320px, centred, with 20px side padding.

### 1. Header (white, shadow `0 2px 4px -2px rgba(46,60,73,0.4)`)
- **Top bar:** min height 80px. Flex row, space-between, wraps on narrow screens.
  - Left: "School bells" at 24px, weight 600, ending in a red full stop (`#e31837`). Next to it, "MUSE controller" at 11px, uppercase, letter-spacing .1em, `#909dab`.
  - Right: a status indicator (an 8×8 square plus a 13px label), then a live clock `HH:MM:SS` at 20px with tabular numerals.
- **Nav bar:** 50px tall, `#2e3c49`. Items are 13px, uppercase, letter-spacing .08em, 30px gap: Today · Schedules · Device · Log. The active item is white with a 3px red bottom border. Inactive items are `#909dab`. Only Today is designed so far.

### 2. Hero (`#2e3c49`, white text, 60px vertical padding)
Two-column grid, `repeat(auto-fit, minmax(min(100%,420px),1fr))`, gap 40px, items aligned to the bottom.
- **Left column:**
  - Eyebrow: "Next bell · {Weekday D Month}" (en-AU), 12px, uppercase, .12em, `#909dab`.
  - Next bell time: `clamp(56px, 9vw, 112px)`, weight 600, line-height 1, tabular numerals.
  - Bell label: 22px, ending in a red full stop.
  - Countdown: `#909dab`. Format is "In 12 min 05 s", or "In 1 h 05 min" when an hour or more away. Once all bells have rung it reads "All bells done for today", and the hero shows the first bell with "… tomorrow".
- **Right column:**
  - While ringing only: a 10×10 red square with a red glow (`0 0 7px 0 rgba(227,24,55,1)`) and the text "Ringing · 1000 Hz · 3 s" (13px, uppercase).
  - Buttons (DS Button): **RING NOW** (red) and **HOLD BELLS** / **RESUME BELLS** (white outline).
  - Note (13px, `#909dab`): "Hold pauses scheduled bells for the rest of today." While held it reads "Scheduled bells are paused until resumed."

### 3. Panel grid (`#e4e5e6` background, 60px vertical padding)
Grid `repeat(auto-fit, minmax(min(100%,380px),1fr))`, gap 20px. Panels are white with a 1px `#e4e5e6` border, **0 radius** and 35px padding.
- **Today's schedule** spans 2 columns on wide screens.
  - Header row: an h2 at 26px, weight 400, "Today's schedule." with a red dot. On the right, "{Schedule name} · {n} bells" at 13px, `#445c6d`.
  - Rows: grid `72px | 1fr | auto`, gap 20px, padding 14px 15px, 1px top border `#e4e5e6`. The time is 17px with tabular numerals. The tag is 11px, uppercase, .1em.
  - Row states:
    - Rung: text `#909dab`, tag "RUNG".
    - Next: background `#fff4f5`, tag "NEXT" in red.
    - Upcoming: text `#2e3c49`, no tag.
    - While held, every un-rung row is tagged "HELD".
- **Right column** (panels stacked, 20px gap):
  - **Bell tone.** Has the MGE red-corner mark: a 40×40 box in the top-right corner with 5px red top and right borders. h3 at 20px bold, "Bell tone." Key/value grid at 14px, keys in `#445c6d`: Frequency 1000 Hz · Duration 3 s · Level −12 dBFS. Below it, a small dark-outline button **PLAY TEST TONE**, with 25px space above.
  - **Audio adapter.** h3 "Audio adapter.", then "Unitek Y-247A USB audio". Key/value grid: USB ID `0d8c:0014` · Format "48 kHz · 2 ch · 16-bit" · Endpoint "0x01 · alt 1" · Last playback "Today HH:MM · N failed transfers".

### 4. Footer
`#2e3c49` with a **20px solid `#e31837` bottom border**. Padding 30px 20px, 13px text in `#909dab`. Left: "school_bells · MUSE Python program". Right: "Madison Group Enterprises".

## Interactions and behaviour
- **Clock and countdown** update every second.
- **Next bell** is the first bell later than now.
- **Ring now / Play test tone:**
  - Call the existing `play_test_tone()` path in `main.py`.
  - Show the ringing state for the length of the tone (3 s), and block repeat presses while it plays.
  - When it finishes, update Last playback with the time and the `errors` count returned by `stream()`.
- **Hold / Resume:** a toggle. While held, scheduled bells don't fire, the status reads "Bells held" with a `#909dab` indicator, and the button label switches to "Resume bells". Suggested rule: a hold clears at midnight.
- **Status indicator:**
  - "Adapter connected" in red when `openByVendorIDAndProductID` succeeds.
  - "Ringing" while a tone plays.
  - "Bells held" while held.
  - Add an error state, "Adapter not found", for when `main.py` logs that error.
- **Hover** (MGE system): 200ms transitions only. Red button backgrounds darken about 4%. Links darken and gain an underline. No scale or bounce effects.
- **Responsive:** grids collapse to a single column below about 420px or 380px. The header and nav wrap or scroll sideways.

## State
- `now`: clock tick.
- `schedule`: the active schedule `{name, bells: [{time:"HH:MM", label}]}`. The prototype has "Standard day" and "Early finish". The real schedules need a storage source.
- `playing`: boolean.
- `hold`: boolean, persisted.
- `adapterStatus`: connected / not found.
- `lastPlayback`: `{time, failedTransfers}`.
- Derived: next bell index, countdown text, and each row's state.

## Design tokens (MGE design system)
- **Colours:**
  - Red `#e31837`: accent and actions only.
  - Dark grey `#2e3c49`: text, header nav, hero, footer.
  - Grey `#445c6d`: secondary text.
  - Medium grey `#909dab`: muted text.
  - Light grey `#e4e5e6`: panel background and borders.
  - White `#ffffff`.
  - Next-row tint `#fff4f5`.
- **Type:**
  - Hurme Geometric Sans 1 (`var(--font-sans)`). Hind is the fallback if Hurme isn't licensed.
  - Body is 15px with line-height 1.6.
  - Buttons are bold, 14px, uppercase, letter-spacing .06em, left-aligned with a `›` in the top-right corner.
- **Spacing:** base unit 20px, small 15px, panel padding 35px, sections 60px.
- **Radius:** 0 everywhere.
- **Shadows:** the header shadow above, and the red glow `0 0 7px 0 rgba(227,24,55,1)`. No other shadows.
- **Signature details:** headings end in a red full stop; the red-corner mark on alternating tiles; the 20px red footer border.

## Assets
There are no images. The fonts are in `_ds/.../fonts/` (Hurme Geometric Sans 1, which has a pageview-capped licence) and the tokens are in `_ds/.../colors_and_type.css`. Button styles are in `_ds/.../_ds_bundle.js` (`window.Button`, variants red / dark / white / outlineDark / outlineWhite).

## Files
- `School Bells.dc.html`: the design reference. Its markup, styles and logic class include the countdown and row-state logic.
- `_ds/madison-group-enterprises-design-system-…/`: MGE tokens, fonts and component bundle.
- Source program: `main.py` (tone generation and USB isochronous playback) and `program.json`.
