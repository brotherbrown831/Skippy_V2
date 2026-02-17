"""Shared UI components and styling for all web pages.

This module provides:
- Design token CSS system used across all pages
- Reusable HTML layout functions
- Common component renderers
"""

# ============================================================================
# DESIGN TOKENS & GLOBAL CSS
# ============================================================================

GLOBAL_STYLES = """
        /* ============================================================================
           DESIGN TOKENS
           ============================================================================ */
        :root {
            --bg-main: #0B1020;
            --bg-secondary: #11162A;
            --bg-tertiary: #1a1d27;
            --border-color: #1F2540;
            --text-main: #E5E7EB;
            --text-muted: #9CA3AF;
            --text-faint: #6B7280;
            --accent-blue: #6366F1;
            --accent-blue-hover: #4F46E5;
            --accent-purple: #A855F7;
            --accent-cyan: #06B6D4;
            --radius-sm: 8px;
            --radius-md: 12px;
            --radius-lg: 14px;
            --shadow-sm: 0 2px 4px rgba(0,0,0,0.15);
            --shadow-md: 0 4px 12px rgba(0,0,0,0.25);
            --shadow-lg: 0 10px 30px rgba(0,0,0,0.35);
            --spacing-2: 4px;
            --spacing-4: 8px;
            --spacing-6: 12px;
            --spacing-8: 16px;
            --spacing-12: 24px;
            --spacing-16: 32px;
            --spacing-24: 48px;
        }

        /* ============================================================================
           BASE STYLES
           ============================================================================ */
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-main);
            color: var(--text-main);
            padding: var(--spacing-12);
            min-height: 100vh;
            line-height: 1.6;
        }

        .container {
            max-width: 1280px;
            margin: 0 auto;
        }

        /* ============================================================================
           PAGE LAYOUT
           ============================================================================ */
        .page-header {
            text-align: center;
            margin-bottom: var(--spacing-16);
        }

        .page-header h1 {
            font-size: 2rem;
            color: var(--accent-blue);
            margin-bottom: var(--spacing-4);
            font-weight: 700;
        }

        .page-header p {
            color: var(--text-muted);
            font-size: 0.95rem;
        }

        .page-controls {
            display: flex;
            gap: var(--spacing-8);
            margin-bottom: var(--spacing-16);
            flex-wrap: wrap;
            align-items: center;
        }

        /* ============================================================================
           UNIFIED BUTTON SYSTEM
           ============================================================================ */
        .btn,
        button,
        a.btn,
        .action-btn,
        .card-button,
        .btn-primary,
        .btn-cancel {
            padding: var(--spacing-6) var(--spacing-8);
            border: none;
            border-radius: var(--radius-md);
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: var(--spacing-6);
            transition: all 0.2s ease;
            text-decoration: none;
        }

        .btn-primary,
        button:not(.btn-ghost):not(.btn-secondary):not(.btn-danger) {
            background: var(--accent-blue);
            color: white;
        }

        .btn-primary:hover,
        button:not(.btn-ghost):not(.btn-secondary):not(.btn-danger):hover {
            background: var(--accent-blue-hover);
            transform: translateY(-1px);
            box-shadow: var(--shadow-md);
        }

        .btn-secondary {
            background: var(--accent-purple);
            color: white;
        }

        .btn-secondary:hover {
            background: #9333EA;
            transform: translateY(-1px);
            box-shadow: var(--shadow-md);
        }

        .btn-ghost,
        .btn-cancel {
            background: transparent;
            border: 1px solid var(--border-color);
            color: var(--text-main);
        }

        .btn-ghost:hover,
        .btn-cancel:hover {
            background: var(--bg-secondary);
            border-color: var(--accent-blue);
            color: var(--text-main);
        }

        .btn-danger {
            background: #EF4444;
            color: white;
        }

        .btn-danger:hover {
            background: #DC2626;
            transform: translateY(-1px);
            box-shadow: var(--shadow-md);
        }

        /* ============================================================================
           TABLE STYLING
           ============================================================================ */
        table {
            width: 100%;
            border-collapse: collapse;
            margin: var(--spacing-12) 0;
        }

        th {
            background: var(--bg-secondary);
            color: var(--text-main);
            padding: var(--spacing-8);
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid var(--border-color);
        }

        td {
            padding: var(--spacing-8);
            border-bottom: 1px solid var(--border-color);
        }

        tr:hover {
            background: var(--bg-secondary);
        }

        /* ============================================================================
           CARDS & CONTENT AREAS
           ============================================================================ */
        .card,
        .section {
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            padding: var(--spacing-12);
            margin-bottom: var(--spacing-12);
            transition: all 0.3s ease;
        }

        .card:hover,
        .section:hover {
            border-color: var(--accent-blue);
            box-shadow: var(--shadow-md);
        }

        .section-title {
            font-size: 1.4rem;
            color: var(--accent-blue);
            margin-bottom: var(--spacing-12);
            font-weight: 700;
        }

        .subsection-title {
            font-size: 1.1rem;
            color: var(--text-main);
            margin-bottom: var(--spacing-8);
            margin-top: var(--spacing-12);
            font-weight: 600;
        }

        /* ============================================================================
           FORM ELEMENTS
           ============================================================================ */
        label {
            display: block;
            color: var(--text-main);
            font-size: 0.85rem;
            font-weight: 600;
            margin: var(--spacing-8) 0 var(--spacing-4) 0;
        }

        input,
        textarea,
        select {
            width: 100%;
            background: var(--bg-secondary);
            color: var(--text-main);
            border: 1px solid var(--border-color);
            padding: var(--spacing-6) var(--spacing-8);
            border-radius: var(--radius-md);
            font-size: 0.9rem;
            transition: all 0.2s ease;
            font-family: inherit;
            margin-bottom: var(--spacing-6);
        }

        input:focus,
        textarea:focus,
        select:focus {
            outline: none;
            border-color: var(--accent-blue);
            background: var(--bg-tertiary);
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
        }

        input::placeholder,
        textarea::placeholder {
            color: var(--text-faint);
        }

        textarea {
            resize: vertical;
            min-height: 80px;
        }

        /* ============================================================================
           MODAL DIALOGS
           ============================================================================ */
        .modal {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
            backdrop-filter: blur(4px);
            animation: fadeIn 0.2s ease;
        }

        @keyframes fadeIn {
            from { opacity: 0; backdrop-filter: blur(0px); }
            to { opacity: 1; backdrop-filter: blur(4px); }
        }

        .modal-content {
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            max-width: 500px;
            width: 95%;
            max-height: 85vh;
            overflow-y: auto;
            box-shadow: var(--shadow-lg);
            animation: slideUp 0.3s ease;
        }

        @keyframes slideUp {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: var(--spacing-12);
            border-bottom: 1px solid var(--border-color);
        }

        .modal-header h3 {
            margin: 0;
            color: var(--accent-blue);
            font-weight: 700;
            font-size: 1.25rem;
        }

        .modal-close {
            background: none;
            border: none;
            color: var(--text-muted);
            font-size: 1.8rem;
            cursor: pointer;
            padding: 0;
            line-height: 1;
            transition: color 0.2s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 32px;
            height: 32px;
            border-radius: var(--radius-md);
        }

        .modal-close:hover {
            color: var(--text-main);
            background: var(--bg-secondary);
        }

        .modal-body {
            padding: var(--spacing-12);
        }

        .modal-footer {
            display: flex;
            justify-content: flex-end;
            gap: var(--spacing-8);
            padding: var(--spacing-12);
            border-top: 1px solid var(--border-color);
        }

        /* ============================================================================
           UTILITY CLASSES
           ============================================================================ */
        .text-muted {
            color: var(--text-muted);
        }

        .text-faint {
            color: var(--text-faint);
        }

        .text-center {
            text-align: center;
        }

        .mt-1 { margin-top: var(--spacing-4); }
        .mt-2 { margin-top: var(--spacing-6); }
        .mt-4 { margin-top: var(--spacing-12); }
        .mb-1 { margin-bottom: var(--spacing-4); }
        .mb-2 { margin-bottom: var(--spacing-6); }
        .mb-4 { margin-bottom: var(--spacing-12); }
        .gap-2 { gap: var(--spacing-6); }
        .gap-4 { gap: var(--spacing-12); }

        .flex {
            display: flex;
        }

        .flex-col {
            flex-direction: column;
        }

        .flex-wrap {
            flex-wrap: wrap;
        }

        .items-center {
            align-items: center;
        }

        .justify-between {
            justify-content: space-between;
        }

        /* ============================================================================
           RESPONSIVE DESIGN
           ============================================================================ */
        @media (max-width: 768px) {
            :root {
                --spacing-12: 16px;
                --spacing-16: 24px;
            }

            body {
                padding: var(--spacing-8);
            }

            .page-header h1 {
                font-size: 1.5rem;
            }

            .page-controls {
                flex-direction: column;
            }

            .page-controls button,
            .page-controls a {
                width: 100%;
                justify-content: center;
            }

            table {
                font-size: 0.85rem;
            }

            th, td {
                padding: var(--spacing-4) var(--spacing-6);
            }
        }

        /* ============================================================================
           LIGHT THEME SUPPORT
           ============================================================================ */
        body.light-theme {
            --bg-main: #F9FAFB;
            --bg-secondary: #F3F4F6;
            --bg-tertiary: #FFFFFF;
            --border-color: #E5E7EB;
            --text-main: #111827;
            --text-muted: #6B7280;
            --text-faint: #9CA3AF;
        }

        body.light-theme .card,
        body.light-theme .section {
            box-shadow: var(--shadow-sm);
        }

        body.light-theme .card:hover,
        body.light-theme .section:hover {
            box-shadow: var(--shadow-md);
        }

        body.light-theme .modal-content {
            box-shadow: var(--shadow-lg);
        }
"""

# ============================================================================
# LAYOUT HELPER FUNCTIONS
# ============================================================================


def render_page_header(title: str, subtitle: str = "") -> str:
    """Render a page header with title and optional subtitle."""
    subtitle_html = f'<p>{subtitle}</p>' if subtitle else ''
    return f'''
    <div class="page-header">
        <h1>{title}</h1>
        {subtitle_html}
    </div>'''


def render_page_controls(*buttons_html: str) -> str:
    """Render page controls (buttons row)."""
    buttons = '\n        '.join(buttons_html)
    return f'''
    <div class="page-controls">
        {buttons}
    </div>'''


def render_section(title: str, content_html: str, id_attr: str = "") -> str:
    """Render a content section."""
    id_str = f' id="{id_attr}"' if id_attr else ''
    return f'''
    <section class="section"{id_str}>
        <h2 class="section-title">{title}</h2>
        {content_html}
    </section>'''


def render_table_row(cells: list[str]) -> str:
    """Render a table row."""
    cells_html = '\n        '.join([f'<td>{cell}</td>' for cell in cells])
    return f'''
        <tr>
            {cells_html}
        </tr>'''


def render_modal(modal_id: str, title: str, body_html: str, footer_buttons_html: str = "") -> str:
    """Render a complete modal dialog."""
    return f'''
    <div id="{modal_id}" class="modal" style="display: none;">
        <div class="modal-content">
            <div class="modal-header">
                <h3>{title}</h3>
                <button class="modal-close" onclick="document.getElementById('{modal_id}').style.display='none'">×</button>
            </div>
            <div class="modal-body">
                {body_html}
            </div>
            {f'<div class="modal-footer">{footer_buttons_html}</div>' if footer_buttons_html else ''}
        </div>
    </div>'''


def render_button(label: str, onclick: str = "", class_name: str = "btn-primary", id_attr: str = "") -> str:
    """Render a button."""
    onclick_attr = f' onclick="{onclick}"' if onclick else ''
    id_str = f' id="{id_attr}"' if id_attr else ''
    return f'<button class="btn {class_name}"{onclick_attr}{id_str}>{label}</button>'


def render_link_button(label: str, href: str, class_name: str = "btn-primary") -> str:
    """Render a link that looks like a button."""
    return f'<a href="{href}" class="btn {class_name}">{label}</a>'


def render_form_field(label: str, input_html: str, required: bool = False) -> str:
    """Render a form field with label."""
    required_mark = " *" if required else ""
    return f'''
        <label>{label}{required_mark}</label>
        {input_html}'''


def render_html_page(
    title: str,
    body_html: str,
    extra_scripts: str = "",
    extra_head: str = ""
) -> str:
    """Render a complete HTML page with design tokens and layout."""
    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title} - Skippy</title>
    <style>
{GLOBAL_STYLES}
    </style>
    {extra_head}
</head>
<body>
    <div class="container">
        {body_html}
    </div>
    {extra_scripts}
</body>
</html>'''
