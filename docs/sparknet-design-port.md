# Claude Code Prompt — Port SPARKNET Design System to Another Platform

## ⚠ Safety contract — read this before touching any file

This task is **purely cosmetic**. You are porting a visual design layer: colours, typography,
theme switching, and accessibility utilities. You must not touch any business logic.

**Hard constraints — violating any of these is a blocking error:**

- Never edit a file that imports from an API client, router, authentication module, or global
  state manager
- Never change routing, link `href`s, form `action`s, or click/submit handlers
- Never touch server-side config, build config (`next.config.*`, `vite.config.*`, `webpack.config.*`),
  environment variables, or CI/CD pipelines
- Never change `data-*` attributes, `js-*` class names, or anything referenced by JavaScript
  selectors — they carry semantic or scripting meaning beyond style
- Never modify existing animations that are part of user-facing interactions (progress bars,
  loading spinners, skeleton screens)
- **If in doubt, do not edit it.**

**If you discover that a required visual change requires touching business logic,** stop, describe
the conflict, and ask before proceeding.

---

## Context

You are adapting the visual design layer from **SPARKNET** (a Next.js 16 / Tailwind v4 / shadcn/ui
platform) into another frontend codebase. The goal is improved typography, colour contrast, theme
switching, and accessibility utilities.

---

## Step 0 — Create a feature branch

Before reading a single source file:

```bash
git checkout -b feat/sparknet-design-system
```

All changes land on this branch. If anything breaks, `git checkout main` restores the working
state. Do not merge until the acceptance checklist passes.

---

## Step 1 — Detect the target stack

The CSS methodology determines where tokens go and how body styles are applied. Identify it first:

```bash
# CSS tooling in package.json
grep -E "tailwind|styled-components|@emotion|sass|postcss" package.json

# Locate the global stylesheet
find . \( -name "globals.css" -o -name "global.css" -o -name "app.css" -o -name "globals.scss" \) \
  | grep -v node_modules | head -10

# Find an existing theme token file
find . \( -name "tokens.css" -o -name "theme.css" -o -name "colors.css" \) \
  | grep -v node_modules | head -10
```

Match the result to the table below — the rest of the steps use the matched approach:

| Stack detected | Where to add tokens | Where to set body styles |
|---|---|---|
| Plain CSS / PostCSS | `globals.css` (top-level) | `body {}` rule in same file |
| Tailwind v3 | `globals.css` inside `@layer base` | `@layer base { body {} }` |
| Tailwind v4 | `globals.css` `@layer base` **or** `@theme inline` for design tokens | `@layer base { body {} }` |
| CSS Modules | Create `styles/design-tokens.css`; import in root layout | Component-level classes referencing vars |
| styled-components / Emotion | `createGlobalStyle` component, mounted in root | Inside `createGlobalStyle` |
| Sass/SCSS | `styles/_tokens.scss`; `@use` in root `globals.scss` | `body {}` in `globals.scss` |

Document which row matches before proceeding.

---

## Step 2 — Audit exactly which files you will change

Read these before writing anything:

1. The global stylesheet (found in Step 1)
2. The root layout — `app/layout.tsx`, `pages/_app.tsx`, or `index.html`
3. The root navigation component (search for `<nav`, `<header`, or `Navbar`/`Header` in the
   component tree)
4. Any existing design token or theme file found in Step 1

Produce an explicit change list. **If the list exceeds 5 files, or if any file imports from an API
client / router / auth module, stop and describe the conflict before proceeding.**

---

## Step 3 — Find the existing localStorage theme key

Search before hardcoding `APP_THEME` — duplicating a key creates split state:

```bash
grep -rn "localStorage\." \
  --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx" \
  . | grep -v node_modules | grep -iE "theme|color|dark|mode|appearance"
```

- If an existing key is found, **use it everywhere** — in the no-flash script, in the hook, in
  the switcher component.
- If no key exists, use `APP_THEME`.

---

## Step 4 — Browser support check

The token system below uses `oklch()` (CSS Color Level 4) and `color-mix()`. Check whether the
project's browser support baseline permits these:

- `oklch()` — Chrome 111+, Firefox 113+, Safari 15.4+ (>95% global coverage as of 2025)
- `color-mix(in oklch, …)` — Chrome 111+, Firefox 113+, Safari 16.2+

If the project targets older browsers, replace `oklch(…)` values with `hsl(…)` equivalents and
replace the `color-mix(…)` nav background with a static `rgba(…)` fallback:

```css
/* Fallback for browsers without oklch support */
@supports not (color: oklch(0 0 0)) {
  :root {
    --background: hsl(210, 40%, 98%);
    --text-primary: hsl(222, 47%, 11%);
    /* … map remaining tokens … */
  }
}
```

---

## Design patterns to extract from SPARKNET

### Token system — OKLCH semantic colour layer

Insert the full block below into the global stylesheet. Do **not** remove existing tokens —
add this as an additive layer and override only what conflicts with the project's existing names.

```css
/* ─── SPARKNET semantic tokens (light mode) ─────────────────────────────── */
:root {
  /* Surfaces */
  --background:        oklch(0.985 0.002 247);
  --surface:           oklch(1 0 0);
  --surface-elevated:  oklch(1 0 0);
  --surface-muted:     oklch(0.965 0.003 247);

  /* Text — all pass WCAG AA (4.5:1) against their paired surface */
  --text-primary:   oklch(0.21  0.02  257);   /* ≈ near-black blue-tinted */
  --text-secondary: oklch(0.42  0.015 257);
  --text-muted:     oklch(0.53  0.012 257);   /* captions / placeholders */

  /* Borders */
  --border: oklch(0.9 0.004 247);

  /* Accent — primary interactive colour (blue-violet) */
  --accent:          oklch(0.55 0.2 264);
  --accent-strong:   oklch(0.47 0.21 264);
  --accent-contrast: oklch(0.985 0 0);        /* text ON an accent background */

  /* Semantic states */
  --success:        oklch(0.62 0.16 150);
  --success-strong: oklch(0.42 0.14 150);
  --success-soft:   oklch(0.95 0.04 150);

  --warning:        oklch(0.74 0.15  75);
  --warning-strong: oklch(0.48 0.12  70);
  --warning-soft:   oklch(0.96 0.05  85);

  --danger:         oklch(0.58 0.22  27);
  --danger-strong:  oklch(0.45 0.2   27);
  --danger-soft:    oklch(0.95 0.04  27);

  --focus-ring:      var(--accent-strong);
  --reading-leading: 1.6;
  --radius:          0.625rem;
}

/* ─── Dark mode ──────────────────────────────────────────────────────────── */
/* Applied as class .dark on <html>. Toggled by the ThemeSwitcher (see §8). */
.dark {
  --background:        oklch(0.16 0.01 257);
  --surface:           oklch(0.205 0.01 257);
  --surface-elevated:  oklch(0.245 0.012 257);
  --surface-muted:     oklch(0.23  0.01 257);

  --text-primary:   oklch(0.97  0.003 247);
  --text-secondary: oklch(0.8   0.01  247);
  --text-muted:     oklch(0.68  0.012 247);

  --border: oklch(0.32 0.012 257);

  --accent:          oklch(0.7  0.16 264);
  --accent-strong:   oklch(0.78 0.15 264);
  --accent-contrast: oklch(0.16 0.01 257);

  --success:        oklch(0.7  0.15 150);
  --success-strong: oklch(0.82 0.16 150);
  --success-soft:   oklch(0.28 0.06 150);

  --warning:        oklch(0.78 0.15  80);
  --warning-strong: oklch(0.88 0.15  85);
  --warning-soft:   oklch(0.32 0.06  75);

  --danger:         oklch(0.7  0.19  27);
  --danger-strong:  oklch(0.82 0.16  22);
  --danger-soft:    oklch(0.3  0.08  27);

  --focus-ring: var(--accent-strong);
}

/* ─── High Contrast — WCAG AAA separation ────────────────────────────────── */
.theme-contrast {
  --background:     oklch(1 0 0);
  --surface:        oklch(1 0 0);
  --surface-muted:  oklch(0.94 0 0);
  --text-primary:   oklch(0.12 0 0);
  --text-secondary: oklch(0.2  0 0);
  --text-muted:     oklch(0.3  0 0);
  --border:         oklch(0.35 0 0);
  --accent:         oklch(0.45 0.24 264);
  --accent-strong:  oklch(0.35 0.26 264);
  --focus-ring:     oklch(0.2  0.26 264);
}
.theme-contrast.dark {
  --background:       oklch(0.08 0 0);
  --surface:          oklch(0.12 0 0);
  --surface-elevated: oklch(0.16 0 0);
  --text-primary:     oklch(1    0    0);
  --text-secondary:   oklch(0.92 0    0);
  --text-muted:       oklch(0.82 0    0);
  --border:           oklch(0.7 0 0);
  --accent:           oklch(0.82 0.16 264);
  --accent-strong:    oklch(0.9  0.14 264);
  --focus-ring:       oklch(0.95 0.1  264);
}

/* ─── Comfortable Reading ────────────────────────────────────────────────── */
.comfortable { --reading-leading: 1.85; }
.comfortable body { line-height: var(--reading-leading); letter-spacing: 0.01em; }

/* ─── Large Font (rem-based UI scales automatically) ─────────────────────── */
.large-font { font-size: 19px; }

/* ─── Reduce motion ──────────────────────────────────────────────────────── */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
    scroll-behavior: auto !important;
  }
}
.reduce-motion *, .reduce-motion *::before, .reduce-motion *::after {
  animation-duration: 0.001ms !important;
  transition-duration: 0.001ms !important;
}
```

---

### Base body + focus ring rules

Add to the global stylesheet (inside `@layer base` for Tailwind projects):

```css
body {
  background-color: var(--background);
  color: var(--text-primary);
  font-family: var(--font-inter, 'Inter'), system-ui, -apple-system, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* Always-visible keyboard focus ring on all interactive elements */
:where(a, button, input, select, textarea, summary, [tabindex]):focus-visible {
  outline: 3px solid var(--focus-ring);
  outline-offset: 2px;
  border-radius: 4px;
}

/* Skip-to-content link — add <a class="skip-link" href="#main">Skip to content</a>
   as the very first child of <body>. The <main id="main"> must exist. */
.skip-link {
  position: absolute;
  left: -9999px;
  top: 4px;
}
.skip-link:focus {
  left: 1rem;
  z-index: 100;
  padding: 0.5rem 1rem;
  background: var(--accent);
  color: var(--accent-contrast);
  border-radius: var(--radius);
  text-decoration: none;
}
```

Also add the skip-link HTML element as the first child of `<body>` (or `<Body>` in Next.js):

```html
<a class="skip-link" href="#main">Skip to content</a>
```

---

### Utility classes

```css
.bg-surface          { background-color: var(--surface); }
.bg-surface-elevated { background-color: var(--surface-elevated); }
.bg-surface-muted    { background-color: var(--surface-muted); }
.text-primary-token  { color: var(--text-primary); }
.text-secondary-token { color: var(--text-secondary); }
.text-muted-token    { color: var(--text-muted); }
.border-token        { border-color: var(--border); }
```

---

### Typography — Inter font

Choose the method that matches the project stack:

**Next.js App Router (preferred):**
```tsx
// app/layout.tsx
import { Inter } from 'next/font/google';
const inter = Inter({ subsets: ['latin'], variable: '--font-inter', display: 'swap' });

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={inter.variable}>
      {children}
    </html>
  );
}
```

**Tailwind v4 (`@theme`):**
```css
@theme inline {
  --font-sans: 'Inter', system-ui, sans-serif;
}
```

**Plain HTML:**
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&display=swap" rel="stylesheet">
```

If the project already uses a sans-serif typeface the team has chosen, **skip this step** and note
it. Do not override a deliberate font choice.

---

### Theme switching — no-flash pattern

#### Pre-hydration script (prevents flash of wrong theme on page load)

The script must run **before the browser renders any content**. Placement differs by framework:

**Plain HTML** — paste directly into `<head>` before all other scripts:
```html
<script>
(function(){try{
  var KEY = 'APP_THEME'; /* ← replace with key found in Step 3 */
  var s = JSON.parse(localStorage.getItem(KEY) || 'null');
  var e = document.documentElement;
  if (!s) {
    var dark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    s = { appearance: dark ? 'dark' : 'light' };
  }
  e.classList.toggle('dark',           s.appearance === 'dark');
  e.classList.toggle('theme-contrast', !!s.highContrast);
  e.classList.toggle('comfortable',    !!s.comfortable);
  e.classList.toggle('large-font',     !!s.largeFont);
  e.classList.toggle('reduce-motion',  !!s.reduceMotion);
  e.style.colorScheme = s.appearance || 'light';
} catch(_) {}}());
</script>
```

**Next.js App Router** — use `<Script strategy="beforeInteractive">` inside `<head>` in
`app/layout.tsx` (raw `<script>` tags are stripped by React):
```tsx
import Script from 'next/script';

// Inside <head>:
<Script id="theme-init" strategy="beforeInteractive">{`
(function(){try{
  var KEY = 'APP_THEME';
  var s = JSON.parse(localStorage.getItem(KEY) || 'null');
  var e = document.documentElement;
  if (!s) {
    var dark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    s = { appearance: dark ? 'dark' : 'light' };
  }
  e.classList.toggle('dark',           s.appearance === 'dark');
  e.classList.toggle('theme-contrast', !!s.highContrast);
  e.classList.toggle('comfortable',    !!s.comfortable);
  e.classList.toggle('large-font',     !!s.largeFont);
  e.classList.toggle('reduce-motion',  !!s.reduceMotion);
  e.style.colorScheme = s.appearance || 'light';
} catch(_) {}}());
`}</Script>
```

**Next.js Pages Router** — use `dangerouslySetInnerHTML` in `_document.tsx`:
```tsx
<script dangerouslySetInnerHTML={{ __html: `/* same script content */` }} />
```

#### React `useTheme` hook

Use this in the ThemeSwitcher component and any other component that needs to read or write theme
settings. Replace `'APP_THEME'` with the key found in Step 3.

```ts
// hooks/use-theme.ts
'use client'; // Next.js App Router only

import { useCallback, useEffect, useState } from 'react';

export interface ThemeSettings {
  appearance: 'light' | 'dark';
  highContrast: boolean;
  comfortable: boolean;
  largeFont: boolean;
  reduceMotion: boolean;
}

const THEME_KEY = 'APP_THEME'; // ← use existing key from Step 3

const DEFAULTS: ThemeSettings = {
  appearance: 'light',
  highContrast: false,
  comfortable: false,
  largeFont: false,
  reduceMotion: false,
};

function readStorage(): ThemeSettings {
  try {
    const raw = localStorage.getItem(THEME_KEY);
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : {
      ...DEFAULTS,
      appearance: window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light',
    };
  } catch {
    return DEFAULTS;
  }
}

function applyToDOM(s: ThemeSettings) {
  const el = document.documentElement;
  el.classList.toggle('dark',           s.appearance === 'dark');
  el.classList.toggle('theme-contrast', s.highContrast);
  el.classList.toggle('comfortable',    s.comfortable);
  el.classList.toggle('large-font',     s.largeFont);
  el.classList.toggle('reduce-motion',  s.reduceMotion);
  el.style.colorScheme = s.appearance;
}

export function useTheme() {
  const [theme, setThemeState] = useState<ThemeSettings>(DEFAULTS);

  useEffect(() => {
    setThemeState(readStorage());
  }, []);

  const setTheme = useCallback((next: Partial<ThemeSettings>) => {
    setThemeState(prev => {
      const updated = { ...prev, ...next };
      try { localStorage.setItem(THEME_KEY, JSON.stringify(updated)); } catch {}
      applyToDOM(updated);
      return updated;
    });
  }, []);

  const toggle = useCallback((key: keyof ThemeSettings) => {
    setTheme({ [key]: key === 'appearance'
      ? (theme.appearance === 'dark' ? 'light' : 'dark')
      : !theme[key] });
  }, [theme, setTheme]);

  return { theme, setTheme, toggle };
}
```

---

### Navigation bar pattern

Key decisions to replicate — **change only colours and layout classes, not routing or handlers**:

```css
.nav {
  position: sticky;
  top: 0;
  z-index: 50;
  width: 100%;
  border-bottom: 1px solid var(--border);
  /* color-mix requires Chrome 111+ / Firefox 113+ / Safari 16.2+.
     Fallback: background-color: rgba(255,255,255,0.85) in .nav; rgba(22,22,35,0.85) in .dark .nav */
  background-color: color-mix(in oklch, var(--surface) 85%, transparent);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.nav-link {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: calc(var(--radius) - 2px);
  color: var(--text-secondary);
  text-decoration: none;
  transition: color 150ms, background-color 150ms;
}
.nav-link:hover,
.nav-link[aria-current="page"] {
  color: var(--accent-strong);
  background-color: var(--surface-muted);
}
.nav-link[aria-current="page"] { font-weight: 600; }

/* Brand gradient — apply to logo text and primary CTA buttons only */
.brand-gradient {
  background: linear-gradient(to right, oklch(0.48 0.22 264), oklch(0.5 0.26 308));
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
.btn-brand {
  background: linear-gradient(to right, oklch(0.48 0.22 264), oklch(0.5 0.26 308));
  color: white;
  border: none;
}
.btn-brand:hover {
  background: linear-gradient(to right, oklch(0.42 0.22 264), oklch(0.44 0.26 308));
}
```

---

### Card elevation system

```css
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.5rem;
}
.card-elevated {
  background: var(--surface-elevated);
  box-shadow: 0 1px 3px oklch(0 0 0 / 0.08), 0 4px 16px oklch(0 0 0 / 0.06);
}
.dark .card-elevated {
  box-shadow: 0 1px 3px oklch(0 0 0 / 0.3), 0 4px 16px oklch(0 0 0 / 0.2);
}
```

---

### Accessible ThemeSwitcher component

The switcher is a dropdown with toggle rows for: Dark mode, High contrast, Comfortable reading,
Large font, Reduce motion. Each row uses `role="switch"` + `aria-checked` (string `"true"`/`"false"`)
for screen reader compatibility.

Wire the `toggle` function from `useTheme` above to each button's `onClick`.

```tsx
// components/ThemeSwitcher.tsx — excerpt showing the accessible toggle pattern
function ToggleRow({ icon, title, desc, checked, onToggle }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked ? 'true' : 'false'}  /* must be string, not boolean */
      onClick={onToggle}
      className="toggle-row"
    >
      <span aria-hidden="true">{icon}</span>
      <span className="toggle-label">
        <span className="toggle-title">{title}</span>
        <span className="toggle-desc">{desc}</span>
      </span>
      <span aria-hidden="true" className="toggle-track" data-checked={String(checked)}>
        <span className="toggle-thumb" />
      </span>
    </button>
  );
}
```

```css
.toggle-row {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  width: 100%;
  padding: 0.5rem;
  border-radius: 6px;
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
}
.toggle-row:hover { background: var(--surface-muted); }
.toggle-track {
  display: inline-flex;
  height: 1.25rem;
  width: 2.25rem;
  align-items: center;
  border-radius: 9999px;
  border: 1px solid var(--border);
  background: var(--surface-muted);
  transition: background 150ms;
  flex-shrink: 0;
}
.toggle-track[data-checked="true"] { background: var(--accent); border-color: var(--accent); }
.toggle-thumb {
  height: 1rem;
  width: 1rem;
  border-radius: 50%;
  background: white;
  transform: translateX(2px);
  transition: transform 150ms;
}
.toggle-track[data-checked="true"] .toggle-thumb { transform: translateX(1.1rem); }
```

---

## Step-by-step execution

1. **Read first.** Read the global stylesheet, root layout, and nav component before writing.
2. **Detect stack** (Step 1) and document which row from the table matches.
3. **Find the existing localStorage key** (Step 2). Use it; don't invent a parallel one.
4. **Check browser support** (Step 4). Add `@supports` fallbacks if required.
5. **Add the token block** (§ Token system). Insert additively — do not remove existing tokens.
6. **Add base body styles** and the focus ring rules (§ Base body).
7. **Add the skip-link HTML element** as the first child of `<body>`.
8. **Set Inter** (§ Typography). Skip if the project has a deliberate font choice.
9. **Wire the no-flash script** (§ Theme switching) using the framework-appropriate method.
10. **Add the `useTheme` hook** to `hooks/use-theme.ts`.
11. **Update the navigation bar** if one exists (§ Nav). Replace hardcoded colours with token
    vars. Do not change routing, hrefs, or handlers.
12. **Audit hardcoded colours** in component files. Run:
    ```bash
    grep -rn --include="*.css" --include="*.scss" --include="*.tsx" --include="*.jsx" \
      -E '#[0-9a-fA-F]{3,8}\b|rgb\(|hsl\(|rgba\(|hsla\(' \
      . | grep -v node_modules | grep -v "\.svg" | grep -v "brand-gradient"
    ```
    Replace each hit with the nearest semantic token. Ignore hardcoded colours inside SVG `fill`/
    `stroke` attributes.
13. **Add a ThemeSwitcher** to the nav or a settings area. Wire it to `useTheme`.
14. **Run the app.** Verify light mode, dark mode, high contrast, keyboard tab navigation, no
    console errors, no layout shifts.
15. **Run the test suite.** Fix any failures caused by your changes. Do not modify test assertions —
    only fix production code.

---

## Rollback

If the test suite fails or the layout is broken and you cannot identify a clean fix within the
scope of cosmetic changes:

```bash
# Discard all working-tree changes on this branch
git checkout -- .

# Or abandon the branch entirely and start fresh
git checkout main
git branch -D feat/sparknet-design-system
```

Do not force-fix a broken layout by modifying business logic.

---

## Acceptance checklist

Run through every item before declaring done. Tools are noted where they apply.

- [ ] **Light mode** — all text passes WCAG AA contrast (4.5:1) against its background.
      Tool: Chrome DevTools → Rendering → Emulate CSS media feature `prefers-color-scheme: light`,
      then Accessibility panel → contrast ratios. Or: `axe` browser extension.
- [ ] **Dark mode** — same check. Toggle `.dark` on `<html>` and re-run axe.
- [ ] **High contrast mode** — `.theme-contrast` class produces visibly stronger separation than
      standard modes.
- [ ] **Tab navigation** — every button, link, input, and interactive element shows a visible
      focus ring. Test by pressing Tab through the page with mouse pointer offscreen.
- [ ] **Skip link** — pressing Tab once on page load shows the "Skip to content" link and
      activating it jumps focus to `<main id="main">`.
- [ ] **No hardcoded colours** in component files (re-run the grep from Step 12 — zero matches).
- [ ] **Theme persists** across reload — set dark mode, reload, verify `.dark` is already on
      `<html>` before React hydrates (check in DevTools Elements panel immediately after load).
- [ ] **First visit** — clear `localStorage`, reload, verify OS `prefers-color-scheme: dark` is
      respected.
- [ ] **Reduced motion** — OS setting `prefers-reduced-motion: reduce` suppresses transitions.
      Test via Chrome DevTools → Rendering → Emulate CSS media feature.
- [ ] **No TypeScript errors** — `tsc --noEmit` (or `next build`) passes clean.
- [ ] **No lint errors** — `eslint` / `ruff` (if applicable) passes clean.
- [ ] **Existing functionality** — all routes load, all forms submit, all API calls succeed.
      Smoke-test the critical user flows manually.
- [ ] **No layout shifts** — check Chrome DevTools Performance panel for CLS > 0 after theme
      script runs.
- [ ] **`color-mix` fallback** (if required by browser target) — nav background degrades
      gracefully on browsers that do not support `color-mix(in oklch, …)`.
