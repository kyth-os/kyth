# Graffiti OS Branding Implementation

## Overview
Create new brand assets for the rename from KythOS to Graffiti OS. These files
will live alongside existing kyth-* files until the full rename in a later phase.

---

## Color Palette — Classic Spray

| Color   | Hex       | Use                      |
|---------|-----------|--------------------------|
| Red     | `#e12c2c` | Primary letter fill      |
| Blue    | `#2a7fff` | Primary letter fill      |
| Yellow  | `#f5c800` | Crown, accent            |
| Green   | `#22b822` | Arrow tail, accent       |
| Purple  | `#9b30ff` | "OS" letters             |
| Shadow  | `#1a1a1a` | 3D offset layer          |
| Keyline | `#ffffff` | Outline / highlight      |
| Dark    | `#0d0d0d` | Wallpaper background     |
| Dark2   | `#111111` | Wallpaper inner gradient |

---

## File 1: `build_files/branding/graffiti-kickoff.svg`
- 64×64 viewBox, KDE Kickoff launcher icon
- Single blockbuster "G" in red gradient
- 3D shadow offset (4,4) in dark grey
- White keyline stroke (2.5px)
- Yellow crown on top (5-pointed, geometric)
- Arrow tail extending bottom-right in green

## File 2: `build_files/branding/graffiti-logo-transparent.svg`
- 400×200 viewBox, transparent background, README header
- "GRAFFITI" across top in blockbuster letters (each ~38×52px)
- "OS" below/offset right, smaller (~48×36px each)
- Letter colors alternating: G(red) R(blue) A(yellow) F(green) F(purple) I(red) T(blue) I(yellow)
- "OS": O(purple) S(red)
- Each letter has 3D shadow + white keyline
- Crown above first "G", stars scattered, small drips on F's and I's

### Letter shapes (blockbuster style — chunky rectangles with rounded joins)
Each letter is a path of thick rectangular bars:

- **G**: Top bar + left bar + bottom bar + right upper section + crossbar
- **R**: Left bar + top bar + middle bar + bottom bar + right leg diagonal
- **A**: Left diagonal + right diagonal + crossbar
- **F**: Top bar + left bar + middle bar
- **F**: Same
- **I**: Single vertical bar
- **T**: Top bar + center vertical
- **I**: Single vertical bar
- **O** (OS): Full rectangle frame with hole
- **S** (OS): Top bar + middle bar + bottom bar with curve connections

LETTER_WIDTH=38, LETTER_HEIGHT=52, GAP=6, START_X=20, START_Y=20
OS_START_X=160, OS_START_Y=96, OS_SIZE=48x36

## File 3: `build_files/branding/graffiti-logo.svg`
- 420×280 viewBox, dark background (`#0d0d0d`)
- Same tag as transparent version, centered
- Tagline "something beautiful made out of nothing" at bottom
  - Font: clean sans-serif, 11px, white/cream, letter-spacing

## File 4: `build_files/branding/graffiti-boot-badge.svg`
- 420×180 viewBox, Plymouth boot screen
- Simplified tag (less detail for boot rendering)
- "Graffiti OS" text below in bold sans-serif (rendered as text, not paths)

## File 5: `build_files/wallpaper/graffiti-wallpaper.svg`
- 1920×1080 viewBox, mural-style spread

### Layers (bottom to top):
1. **Background**: radial gradient (center #111111 → edges #0d0d0d)
2. **Halo glow**: large ellipse behind main piece, yellow/white blur
3. **Main tag**: full "Graffiti OS" piece centered, ~600px wide, with 3D shadow and keyline
4. **Corner tags**: 4 small "G" throw-ups in each corner, each a different single color
   - Top-left: red, Top-right: blue, Bottom-left: green, Bottom-right: purple
5. **Splatter**: circle clusters along bottom 200px, varying sizes (2-20px radii)
   - Colors: red, blue, green, purple, yellow
6. **Drips**: vertical teardrops hanging from bottom of letters
7. **Tagline**: "something beautiful made out of nothing" at bottom center
   - y=1010, font-size=16, white, sans-serif

### Splatter circle distribution:
- Bottom band from y=880 to y=1080
- ~50-60 circles of varying radii (2-20px)
- Clustered near edges, sparse in center
- 5-10 small circles scattered elsewhere for overspray

---

## Implementation Order
1. `graffiti-kickoff.svg` — simplest, immediate visual win
2. `graffiti-logo-transparent.svg` — most important brand asset
3. `graffiti-logo.svg` — variant with dark bg
4. `graffiti-boot-badge.svg` — boot screen
5. `graffiti-wallpaper.svg` — mural
6. `cockpit-branding.css` — final polish
