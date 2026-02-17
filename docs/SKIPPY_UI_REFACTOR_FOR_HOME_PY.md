# Skippy UI Refactor — Targeting home.py Single HTML Template

## Context

The FastAPI dashboard currently renders a **single massive HTML string** named:

HOMEPAGE_HTML

inside:

home.py

This HTML includes:

* Inline CSS (~500+ lines)
* Inline JavaScript (~800+ lines)
* Multiple modal dialogs
* Dashboard cards grid
* Search UI
* Health badge
* Activity timeline
* Chart.js graphs

The backend endpoints work correctly.

This task is to **modernize and refactor the UI only**.

DO NOT change:

* FastAPI routes
* database queries
* API paths
* Fetch logic behavior
* returned JSON structures

---

## PRIMARY OBJECTIVES

### 1. Break the giant HTML string into structured render functions

Create Python helpers above HOMEPAGE_HTML:

```
def render_base_layout(content: str, extra_scripts: str = "") -> str
def render_modal(id: str, title: str, body: str, footer: str) -> str
def render_dashboard_card(icon, title, desc, stats_html, link, accent)
def render_stat(label, value_id)
def render_section(title, content)
```

Then rebuild HOMEPAGE_HTML using these helpers.

The goal is:

* reduce duplication
* improve readability
* allow consistent UI styling

---

### 2. Replace current CSS with a Design Token System

Move ALL CSS into one `<style>` block at top.

Add this FIRST:

```
:root{
 --bg-main:#0B1020;
 --bg-card:#11162A;
 --border:#1F2540;
 --text-main:#E5E7EB;
 --text-muted:#9CA3AF;
 --accent:#6366F1;
 --accent-hover:#4F46E5;
 --radius:12px;
 --shadow:0 10px 30px rgba(0,0,0,0.25);
}
```

Then refactor existing classes to use variables.

Remove hardcoded colors like:

#1a1d27
#2a2d37
#7eb8ff
etc.

---

### 3. Modernize Layout Structure

Replace:

.container centered layout

with:

```
<div class="app">
  <header class="topbar">...</header>
  <main class="page">
     <div class="page-header">...</div>
     <div class="page-content">...</div>
  </main>
</div>
```

Add consistent:

* 32px page padding
* max width 1280px
* spacing using 8px increments

---

### 4. Redesign Dashboard Cards

Current cards feel dated.

New card style must include:

* subtle gradient or clean flat background
* larger icon circle
* bold metric numbers
* hover lift animation
* rounded 14px corners
* consistent CTA button

Keep same links and stat IDs.

Do NOT change:

memories-total
people-total
tasks-total
etc.

---

### 5. Standardize Buttons

Replace:

.action-btn-primary
.action-btn-secondary
.card-button
.btn-primary

with unified system:

```
.btn
.btn-primary
.btn-secondary
.btn-ghost
.btn-danger
```

All buttons must share:

* same padding
* same radius
* consistent hover animation

---

### 6. Modern Modal Styling

All modals currently duplicated.

Refactor so:

* modal wrapper style shared
* header/body/footer styles shared
* close button consistent

Improve:

* softer shadow
* slightly larger radius
* smoother overlay

Do NOT change modal IDs or JS handlers.

---

### 7. Improve Search UI

Modernize:

* search input with icon inside field
* floating results dropdown
* better hover state

Keep:

id="global-search"
id="search-results"

---

### 8. Improve Activity Timeline

Make activity items:

* card-like rows
* left colored icon bubble
* right content stack

Spacing must match dashboard cards.

---

### 9. Improve Charts Section

Wrap each chart in:

```
.card.chart-card
```

Add:

* consistent header typography
* spacing alignment
* unified background

DO NOT change Chart.js initialization code.

---

### 10. Maintain Vanilla JS

You MUST:

* keep Fetch API
* keep inline script structure
* NOT add frameworks
* NOT add build steps

You MAY:

* reorganize functions
* group JS into logical sections
* add small helper functions

---

## IMPLEMENTATION ORDER (MANDATORY)

Claude must:

1. Extract CSS tokens + modern base styles
2. Create Python render helper functions
3. Refactor cards using helpers
4. Refactor modals using helpers
5. Rebuild HOMEPAGE_HTML using layout wrapper
6. Keep JS functional
7. Show final refactored code

---

## DEFINITION OF DONE

* UI visually consistent
* modern SaaS look
* no backend breakage
* code shorter + modular
* CSS token-based
* reusable modal/card renderers exist

---

## FINAL INSTRUCTION

Refactor home.py following this specification.
Make safe structural improvements first, then visual improvements.
Show the updated Python code with helper functions and new HOMEPAGE_HTML.
