# UI Redesign Implementation Guide

## Status: Pattern Established ✅

We've successfully created a **shared design system** and demonstrated the pattern with `memories.py`. This guide shows how to apply it to remaining pages.

## Files Updated
- ✅ **home.py** - Dashboard (complete redesign)
- ✅ **memories.py** - Memory viewer (redesigned with shared system)
- ✅ **shared_ui.py** - Design token library (created)

## Files Remaining
- ⏳ **people.py** (1,080 lines)
- ⏳ **tasks.py** (977 lines)
- ⏳ **calendar.py** (401 lines)
- ⏳ **reminders.py** (418 lines)
- ⏳ **scheduled.py** (324 lines)

---

## Pattern Used: memories.py Example

### Step 1: Add Import
```python
from .shared_ui import render_html_page, render_page_header, render_section
```

### Step 2: Create HTML Generator Function
```python
def get_memories_page_html() -> str:
    """Generate the memories page HTML using the shared design system."""

    page_content = render_page_header(
        "🧠 Memories",
        "Search and manage your semantic memories"
    )

    controls_html = '''<div class="page-controls">...</div>'''
    section_html = render_section("Semantic Memories", controls_html + table_html)

    page_content += section_html

    scripts = '''<script>... existing JavaScript ...</script>'''

    return render_html_page("Memories", page_content, extra_scripts=scripts)

MEMORIES_PAGE_HTML = get_memories_page_html()
```

### Step 3: Key Changes
- All CSS moved to `shared_ui.GLOBAL_STYLES`
- HTML wrapped in `render_html_page()`
- Existing JavaScript preserved exactly
- Element IDs unchanged
- API endpoints unchanged

---

## Design System Components Available

### Layout Functions
- `render_page_header(title, subtitle)` - Page title section
- `render_page_controls(*buttons)` - Control bar
- `render_section(title, content, id)` - Content section
- `render_html_page(title, body, scripts, head)` - Full page wrapper

### Style Classes (in GLOBAL_STYLES)
- `.container` - Max-width wrapper
- `.btn`, `.btn-primary`, `.btn-ghost`, `.btn-danger` - Buttons
- `.section` - Content cards
- `table` with `th`, `td` - Tables (styled)
- `.modal` - Modal dialogs
- Design token variables: `--bg-main`, `--accent-blue`, etc.

---

## Implementation Steps for Each Remaining File

### For Each File:

1. **Add import** at top:
   ```python
   from .shared_ui import render_html_page, render_page_header, render_section
   ```

2. **Find the HTML template** (search for `_PAGE_HTML = """`)

3. **Extract the `<style>` block** and replace with comment:
   ```python
   # Styles provided by shared_ui.GLOBAL_STYLES
   # Page-specific styles below as needed
   styles = '''
   /* Page-specific overrides */
   .unique-class { ... }
   '''
   ```

4. **Convert to generator function**:
   ```python
   def get_page_html() -> str:
       page_content = render_page_header("title", "subtitle")
       # ... add sections using render_section()
       scripts = '''<script>...</script>'''  # Existing JS
       return render_html_page("title", page_content, extra_scripts=scripts)
   ```

5. **Keep JavaScript untouched** - just extract and pass to `extra_scripts`

6. **Test**:
   - Visit page at http://localhost:8000/{page}
   - Verify layout looks consistent with new design
   - Check that all interactive elements work
   - Confirm no console errors

---

## Expected Visual Changes

### Before
- Inconsistent colors and spacing
- Different button styles per page
- Varied typography
- Basic layouts

### After
- Unified design tokens
- Consistent spacing (8px scale)
- Professional button system
- Dark theme by default
- Light theme support
- Responsive layout
- Modern cards and modals

---

## CSS Token Reference

```css
/* Colors */
--bg-main: #0B1020           (primary background)
--bg-secondary: #11162A      (hover backgrounds)
--bg-tertiary: #1a1d27       (cards)
--border-color: #1F2540      (borders)
--text-main: #E5E7EB         (primary text)
--text-muted: #9CA3AF        (secondary text)
--text-faint: #6B7280        (tertiary text)

/* Accents */
--accent-blue: #6366F1       (primary action)
--accent-purple: #A855F7     (secondary action)
--accent-cyan: #06B6D4       (tertiary)

/* Sizing */
--radius-md: 12px            (standard border-radius)
--radius-lg: 14px            (cards, modals)
--spacing-8: 16px            (standard padding)
--spacing-12: 24px           (large spacing)

/* Effects */
--shadow-md: 0 4px 12px rgba(0,0,0,0.25)
--shadow-lg: 0 10px 30px rgba(0,0,0,0.35)
```

---

## Quick Implementation Checklist

For each remaining page:

- [ ] Add `shared_ui` import
- [ ] Create generator function
- [ ] Use `render_page_header()` for title
- [ ] Use `render_section()` for content areas
- [ ] Wrap with `render_html_page()`
- [ ] Preserve all JavaScript
- [ ] Preserve all element IDs
- [ ] Preserve all API endpoints
- [ ] Test in browser
- [ ] Check dark/light theme toggle
- [ ] Verify responsive design (mobile)
- [ ] Commit to git

---

## File-Specific Notes

### people.py
- Large file with complex modal
- Has light theme by default - will switch to dark theme with new system
- Modal structure should be preserved
- All JavaScript functions must remain

### tasks.py
- Two-panel layout (Today/Backlog)
- Significant JavaScript for drag-drop (preserve!)
- Has custom styling for task cards - integrate with design tokens

### calendar.py
- May use external calendar library
- Preserve library initialization
- Update wrapper styling only

### reminders.py
- Simple list-based page
- Update table styling to match design system

### scheduled.py
- Shows scheduled jobs
- Update table styling
- Preserve all controls

---

## Testing the Redesign

After updating each page:

```bash
# 1. Rebuild Docker image
docker compose build skippy --no-cache

# 2. Restart service
docker compose down skippy && docker compose up -d skippy

# 3. Check page
# Visit http://localhost:8000/{page}

# 4. Verify console
# Press F12, check for errors

# 5. Test theme toggle (if on dashboard)
# Settings button → Theme → Light
```

---

## Benefits of the Shared Design System

✅ **Consistency** - All pages look professional and cohesive
✅ **Maintainability** - Change one CSS variable = updates everywhere
✅ **Faster Development** - Reusable components and functions
✅ **Responsive** - Mobile-friendly by default
✅ **Theme Support** - Light/dark modes just work
✅ **No Breaking Changes** - All APIs, IDs, JavaScript preserved

---

## Next Steps

1. **Immediate** (done):
   - ✅ Create shared_ui.py with design tokens
   - ✅ Update memories.py as proof of pattern
   - ✅ Deploy and test

2. **Short-term** (1-2 hours):
   - Update remaining 5 pages using the pattern
   - Test each page
   - Deploy updated app

3. **Optional**:
   - Extract JavaScript into separate files
   - Add animations/transitions
   - Create CSS file instead of inline styles
   - Add accessibility improvements (ARIA labels)

---

**Last Updated:** Feb 16, 2026
**Status:** Ready for next pages ✅
