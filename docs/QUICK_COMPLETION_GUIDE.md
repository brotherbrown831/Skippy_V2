# UI Redesign - Quick Completion Guide

## Status: 50% Complete ✅

### What's Working Now
- ✅ **shared_ui.py** - Design system (350+ lines, ready to use)
- ✅ **home.py** - Fully redesigned dashboard
- ✅ **memories.py** - Converted to shared system (proven pattern)
- ✅ **calendar.py** - Converted to shared system (second example)
- ⏳ **reminders.py** - Import ready
- ⏳ **scheduled.py** - Import ready
- ⏳ **tasks.py** - Import ready
- ⏳ **people.py** - Import ready

### Remaining Work

All 4 remaining files follow the EXACT SAME PATTERN. Each takes ~10-15 minutes.

### Copy-Paste Template (Use for reminders.py, scheduled.py, tasks.py, people.py)

Find where your `_PAGE_HTML = """<!DOCTYPE html>` starts, and replace with:

```python
def get_page_html() -> str:
    """Generate page using shared design system."""

    page_content = render_page_header("📌 Page Title", "Optional subtitle")

    # Your content sections here
    content_html = '''
        <div>... your existing page layout ...</div>
    '''
    section_html = render_section("Section Title", content_html)

    page_content += section_html

    # Extract existing JavaScript EXACTLY as-is
    scripts = '''
    <script>
        // Your existing JavaScript code here
    </script>
    '''

    # Optional: Page-specific styles
    styles = '''<style>.custom-class { ... }</style>'''

    return render_html_page("Page Title", page_content, extra_scripts=scripts, extra_head=styles)


PAGE_HTML = get_page_html()
```

### Step-by-Step for Each File

1. **Copy existing JavaScript** from the old `_PAGE_HTML` template
2. **Extract main HTML structure** (what goes in the `<body>`)
3. **Wrap with `render_page_header()`** for title
4. **Wrap content sections with `render_section()`**
5. **Paste JavaScript into `scripts` variable**
6. **Replace old `_PAGE_HTML = """...` with `PAGE_HTML = get_page_html()`
7. **Delete the old HTML template string** (everything between `"""` markers)
8. **Test at `http://localhost:8000/{page}`**

### Estimated Time to Complete

- **reminders.py**: ~10 min (simple list-based)
- **scheduled.py**: ~10 min (table-based)
- **tasks.py**: ~15 min (complex JavaScript)
- **people.py**: ~15 min (large file, modals)

**Total: ~50 minutes**

### Actual Code Examples

#### reminders.py (Simple Example)
```python
def get_reminders_html() -> str:
    page_content = render_page_header("🔔 Reminders", "Manage notifications")

    content = '<div id="reminders-list">Loading...</div>'
    section = render_section("Pending Reminders", content)

    page_content += section

    scripts = '''<script>
        async function loadReminders() {
            const res = await fetch('/api/reminders/pending');
            const data = await res.json();
            // ... existing code ...
        }
        loadReminders();
    </script>'''

    return render_html_page("Reminders", page_content, extra_scripts=scripts)

REMINDERS_PAGE_HTML = get_reminders_html()
```

#### tasks.py (Complex Example with custom styles)
```python
def get_tasks_html() -> str:
    page_content = render_page_header("✓ Tasks", "Manage your todo list")

    # Today section
    today_html = '<div id="today-tasks" class="tasks-panel">...</div>'
    today_section = render_section("Today", today_html)

    # Backlog section
    backlog_html = '<div id="backlog-tasks" class="tasks-panel">...</div>'
    backlog_section = render_section("Backlog", backlog_html)

    page_content += today_section + backlog_section

    # ALL existing JavaScript unchanged
    scripts = '''<script>
        async function loadTasks() { ... }
        async function createTask() { ... }
        // All your existing functions
    </script>'''

    # Page-specific styles
    styles = '''<style>
        .tasks-panel { display: flex; flex-direction: column; gap: var(--spacing-8); }
        .task-card { background: var(--bg-secondary); padding: var(--spacing-8); border-radius: var(--radius-md); }
    </style>'''

    return render_html_page("Tasks", page_content, extra_scripts=scripts, extra_head=styles)

TASKS_PAGE_HTML = get_tasks_html()
```

### After Each File Update

```bash
# Rebuild and test
docker compose build skippy --no-cache
docker compose down skippy && docker compose up -d skippy

# Visit the page
http://localhost:8000/{page}

# Check console (F12)
```

### Critical: Element ID Preservation

All existing element IDs in your JavaScript MUST stay the same:
- `document.getElementById('todayEvents')` ← Keep this ID in HTML
- `document.getElementById('reminderForm')` ← Keep this ID in HTML
- etc.

The `render_section()` helper doesn't touch your internal HTML structure - only wraps it.

### Quality Checklist Per File

- [ ] Page loads without errors (F12 console)
- [ ] All interactive elements work (buttons, modals, forms)
- [ ] Data loads from API endpoints
- [ ] Layout looks modern and consistent
- [ ] Responsive design works (resize browser)
- [ ] Dark/Light theme toggle works (if on home)

### Files That Are Already Updated

1. **shared_ui.py** (350 lines)
   - All CSS tokens
   - All layout helpers
   - Ready to use

2. **home.py** (2,783 lines)
   - Fully redesigned
   - Modern dashboard aesthetic
   - All functionality preserved

3. **memories.py** (242 lines)
   - Refactored with shared system
   - Shows the pattern
   - All JavaScript working

4. **calendar.py** (192 lines)
   - Refactored with shared system
   - Two-column layout
   - Event loading working

### To Deploy

```bash
# Build and restart
docker compose build skippy --no-cache
docker compose restart skippy

# Test all pages
http://localhost:8000/
http://localhost:8000/memories
http://localhost:8000/calendar
http://localhost:8000/reminders      ← Not updated yet
http://localhost:8000/scheduled      ← Not updated yet
http://localhost:8000/tasks          ← Not updated yet
http://localhost:8000/people         ← Not updated yet
```

### Getting Help

If you get stuck on any file:

1. **Copy exact JavaScript** from old template
2. **Use `render_page_header()` for title**
3. **Use `render_section()` for each content area**
4. **Paste scripts variable exactly**
5. **Call `render_html_page()`**

Reference working examples: `memories.py` and `calendar.py`

---

**Estimated Total Time to Complete: 50 minutes**
**Difficulty: Straightforward (copy-paste pattern)**
**Risk: None (only styling/layout, no functionality changes)**
