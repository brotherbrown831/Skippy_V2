import logging
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from .shared_ui import render_html_page, render_page_header, render_section

logger = logging.getLogger("skippy")

router = APIRouter()


@router.get("/tasks", response_class=HTMLResponse)
async def tasks_page():
    """Serve the tasks management page."""
    return TASKS_PAGE_HTML


def get_tasks_html() -> str:
    """Generate tasks page using shared design system."""

    page_content = render_page_header(
        "✅ Tasks",
        "Manage your tasks and stay organized"
    )

    # Add task button
    controls_html = '''
        <div class="page-controls">
            <button class="btn btn-primary" onclick="openAddTaskModal()" style="margin-right: var(--spacing-8);">+ Add Task</button>
            <a href="/" class="btn btn-ghost">← Back to Dashboard</a>
        </div>'''

    # Today's tasks section
    today_html = '''
        <div class="page-controls" style="margin-bottom: var(--spacing-12); display: flex; gap: var(--spacing-8);">
            <button class="filter-btn active" onclick="filterTodayTasks('all')" style="background: var(--accent-blue); color: white; border: none; padding: var(--spacing-4) var(--spacing-8); border-radius: var(--radius-sm); cursor: pointer; font-size: 0.9rem;">All (<span id="today-count">0</span>)</button>
            <button class="filter-btn" onclick="filterTodayTasks('due-today')" style="background: var(--bg-tertiary); color: var(--text-main); border: 1px solid var(--border-color); padding: var(--spacing-4) var(--spacing-8); border-radius: var(--radius-sm); cursor: pointer; font-size: 0.9rem;">Due Today</button>
            <button class="filter-btn" onclick="filterTodayTasks('in-progress')" style="background: var(--bg-tertiary); color: var(--text-main); border: 1px solid var(--border-color); padding: var(--spacing-4) var(--spacing-8); border-radius: var(--radius-sm); cursor: pointer; font-size: 0.9rem;">In Progress</button>
            <button class="filter-btn" onclick="filterTodayTasks('blocked')" style="background: var(--bg-tertiary); color: var(--text-main); border: 1px solid var(--border-color); padding: var(--spacing-4) var(--spacing-8); border-radius: var(--radius-sm); cursor: pointer; font-size: 0.9rem;">Blocked</button>
        </div>
        <div id="today-tasks" style="display: grid; gap: var(--spacing-8);"></div>'''

    # Backlog section
    backlog_html = '''
        <input type="text" id="backlog-search" placeholder="Search backlog..." style="width: 100%; padding: var(--spacing-8); background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-md); color: var(--text-main); margin-bottom: var(--spacing-12); font-size: 0.95rem;">
        <div style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: var(--spacing-8);">Total: <span id="backlog-count">0</span> tasks</div>
        <div id="backlog-tasks" style="display: grid; gap: var(--spacing-8);"></div>'''

    page_content += controls_html
    page_content += render_section("📌 Today", today_html)
    page_content += render_section("📚 Backlog", backlog_html)

    # Modal HTML
    modal_html = '''
        <div id="addTaskModal" class="modal" style="display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.6); align-items: center; justify-content: center;">
            <div class="modal-content" style="background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius-lg); padding: var(--spacing-16); max-width: 500px; width: 90%;">
                <h2 style="color: var(--accent-blue); margin-bottom: var(--spacing-12); font-size: 1.4rem;">Add New Task</h2>
                <form onsubmit="submitAddTask(event)">
                    <div style="margin-bottom: var(--spacing-12);">
                        <label style="display: block; color: var(--text-main); font-weight: 500; margin-bottom: var(--spacing-4);">Title</label>
                        <input type="text" id="task-title" required style="width: 100%; padding: var(--spacing-8); background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-md); color: var(--text-main); font-size: 0.9rem;">
                    </div>
                    <div style="margin-bottom: var(--spacing-12);">
                        <label style="display: block; color: var(--text-main); font-weight: 500; margin-bottom: var(--spacing-4);">Description</label>
                        <textarea id="task-description" rows="3" style="width: 100%; padding: var(--spacing-8); background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-md); color: var(--text-main); font-size: 0.9rem; font-family: inherit;"></textarea>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--spacing-8); margin-bottom: var(--spacing-12);">
                        <div>
                            <label style="display: block; color: var(--text-main); font-weight: 500; margin-bottom: var(--spacing-4);">Priority</label>
                            <select id="task-priority" style="width: 100%; padding: var(--spacing-8); background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-md); color: var(--text-main); font-size: 0.9rem;">
                                <option value="0">Low</option>
                                <option value="1">Medium</option>
                                <option value="2">High</option>
                            </select>
                        </div>
                        <div>
                            <label style="display: block; color: var(--text-main); font-weight: 500; margin-bottom: var(--spacing-4);">Due Date</label>
                            <input type="date" id="task-due-date" style="width: 100%; padding: var(--spacing-8); background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-md); color: var(--text-main); font-size: 0.9rem;">
                        </div>
                    </div>
                    <div style="margin-bottom: var(--spacing-12);">
                        <label style="display: block; color: var(--text-main); font-weight: 500; margin-bottom: var(--spacing-4);">Project</label>
                        <input type="text" id="task-project" style="width: 100%; padding: var(--spacing-8); background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-md); color: var(--text-main); font-size: 0.9rem;">
                    </div>
                    <div style="display: flex; gap: var(--spacing-8); justify-content: flex-end;">
                        <button type="button" class="btn btn-ghost" onclick="closeAddTaskModal()">Cancel</button>
                        <button type="submit" class="btn btn-primary">Add Task</button>
                    </div>
                </form>
            </div>
        </div>'''

    # All JavaScript from original
    scripts = '''
    <script>
        let allTodayTasks = [];
        let allBacklogTasks = [];
        let currentTodayFilter = 'all';

        function getStatusColor(status) {
            const colors = {
                'inbox': '#888',
                'next_up': '#4299e1',
                'in_progress': '#805ad5',
                'done': '#48bb78',
                'blocked': '#f56565'
            };
            return colors[status] || '#888';
        }

        function formatDate(dateStr) {
            if (!dateStr) return '';
            const date = new Date(dateStr);
            return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        }

        function formatDueDate(dateStr) {
            if (!dateStr) return '';
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            const date = new Date(dateStr);
            date.setHours(0, 0, 0, 0);
            const diff = date - today;
            const days = Math.ceil(diff / (1000 * 60 * 60 * 24));

            if (days === 0) return 'due-today';
            if (days === 1) return 'tomorrow';
            if (days === -1) return 'overdue';
            if (days < -1) return 'overdue';
            if (days > 1 && days <= 7) return 'this-week';
            return 'later';
        }

        function createTaskCard(task, isBacklog = false) {
            const card = document.createElement('div');
            card.className = 'task-card';
            card.style.cssText = 'background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: var(--spacing-12); cursor: pointer; transition: all 0.2s;';

            const dueDateStr = task.due_date ? formatDate(task.due_date) : '';
            const dueClass = task.due_date ? formatDueDate(task.due_date) : '';
            const overdue = dueClass === 'overdue';
            const dueTodayClass = dueClass === 'due-today' ? 'var(--text-muted)' : overdue ? '#f56565' : 'var(--text-main)';

            const priorityColors = { 0: '#888', 1: '#fbbc04', 2: '#f56565' };
            const priorityLabels = { 0: 'Low', 1: 'Medium', 2: 'High' };
            const statusColor = getStatusColor(task.status);

            const badgesHtml = `
                <span style="display: inline-block; background: ${priorityColors[task.priority]}; color: ${task.priority === 1 ? '#000' : '#fff'}; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; margin-right: 6px; font-weight: 600;">${priorityLabels[task.priority]}</span>
                <span style="display: inline-block; color: ${statusColor}; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600;">${task.status.replace('_', ' ').toUpperCase()}</span>
                ${task.project ? `<span style="display: inline-block; background: var(--accent-purple); color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; margin-left: 6px; font-weight: 600;">${task.project}</span>` : ''}
            `;

            card.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: var(--spacing-8);">
                    <div style="flex: 1;">
                        <div style="color: var(--text-main); font-weight: 600; font-size: 1rem; margin-bottom: var(--spacing-4);">${task.title}</div>
                    </div>
                    ${!isBacklog ? `<input type="checkbox" onchange="toggleTaskComplete(${task.task_id}, this.checked)" style="margin-left: var(--spacing-8);">` : ''}
                </div>
                <div class="task-badges" style="margin-bottom: var(--spacing-8);">
                    ${badgesHtml}
                </div>
                ${dueDateStr ? `<div class="task-meta" style="margin-bottom: var(--spacing-8);\"><span style="color: ${dueTodayClass}; font-size: 0.85rem;">${dueDateStr}</span></div>` : ''}
                <div class="task-details" style="display: none;">
                    ${task.description ? `<div class="task-description" style="color: var(--text-muted); font-size: 0.9rem; margin-bottom: var(--spacing-8);">${task.description}</div>` : ''}
                    <div class="task-actions" style="display: flex; gap: var(--spacing-4); flex-wrap: wrap;">
                        ${!isBacklog ? `<button class="action-btn complete btn btn-primary" onclick="completeTask(${task.task_id})" style="font-size: 0.85rem; padding: 4px 12px;">✓ Complete</button>` : ''}
                        ${isBacklog ? `<button class="action-btn promote btn btn-secondary" onclick="promoteTask(${task.task_id})" style="font-size: 0.85rem; padding: 4px 12px;">↑ Promote</button>` : `<button class="action-btn defer btn btn-secondary" onclick="showDeferDialog(${task.task_id})" style="font-size: 0.85rem; padding: 4px 12px;">⏸ Defer</button>`}
                        ${!isBacklog && task.status !== 'blocked' ? `<button class="action-btn btn btn-danger" onclick="updateTaskStatus(${task.task_id}, 'blocked')" style="font-size: 0.85rem; padding: 4px 12px;">🚫 Block</button>` : ''}
                        <button class="action-btn delete btn btn-danger" onclick="deleteTask(${task.task_id})" style="font-size: 0.85rem; padding: 4px 12px;">🗑 Delete</button>
                    </div>
                </div>
            `;

            card.onclick = (e) => {
                if (e.target.tagName !== 'BUTTON' && e.target.tagName !== 'INPUT') {
                    card.classList.toggle('expanded');
                    const details = card.querySelector('.task-details');
                    if (details) {
                        details.style.display = details.style.display === 'none' ? 'block' : 'none';
                    }
                }
            };

            return card;
        }

        async function loadTodayTasks() {
            try {
                const response = await fetch('/api/tasks/today');
                const data = await response.json();
                allTodayTasks = data.tasks || [];
                document.getElementById('today-count').textContent = allTodayTasks.length;
                filterTodayTasks('all');
            } catch (error) {
                console.error('Error loading today tasks:', error);
                document.getElementById('today-tasks').innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: var(--spacing-12);">❌ Error loading tasks</div>';
            }
        }

        async function loadBacklogTasks() {
            try {
                const response = await fetch('/api/tasks/backlog');
                const data = await response.json();
                allBacklogTasks = data.tasks || [];
                document.getElementById('backlog-count').textContent = allBacklogTasks.length;
                renderBacklogTasks();
            } catch (error) {
                console.error('Error loading backlog:', error);
                document.getElementById('backlog-tasks').innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: var(--spacing-12);">❌ Error loading backlog</div>';
            }
        }

        function filterTodayTasks(filter) {
            currentTodayFilter = filter;

            if (event && event.target) {
                document.querySelectorAll('.filter-btn').forEach(btn => {
                    btn.style.background = 'var(--bg-tertiary)';
                    btn.style.color = 'var(--text-main)';
                    btn.style.border = '1px solid var(--border-color)';
                });
                event.target.style.background = 'var(--accent-blue)';
                event.target.style.color = 'white';
                event.target.style.border = 'none';
            }

            let filtered = allTodayTasks;
            if (filter === 'due-today') {
                filtered = allTodayTasks.filter(t => formatDueDate(t.due_date) === 'due-today');
            } else if (filter === 'in-progress') {
                filtered = allTodayTasks.filter(t => t.status === 'in_progress');
            } else if (filter === 'blocked') {
                filtered = allTodayTasks.filter(t => t.status === 'blocked');
            }

            renderTodayTasks(filtered);
        }

        function renderTodayTasks(tasks) {
            const container = document.getElementById('today-tasks');
            if (tasks.length === 0) {
                container.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: var(--spacing-12);">✨ No tasks today!</div>';
                return;
            }

            container.innerHTML = '';
            tasks.forEach(task => {
                container.appendChild(createTaskCard(task, false));
            });
        }

        function renderBacklogTasks(searchQuery = '') {
            const container = document.getElementById('backlog-tasks');
            let filtered = allBacklogTasks;

            if (searchQuery) {
                filtered = allBacklogTasks.filter(t =>
                    t.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
                    (t.description && t.description.toLowerCase().includes(searchQuery.toLowerCase())) ||
                    (t.project && t.project.toLowerCase().includes(searchQuery.toLowerCase()))
                );
            }

            if (filtered.length === 0) {
                container.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: var(--spacing-12);">📭 Empty backlog</div>';
                return;
            }

            container.innerHTML = '';
            filtered.forEach(task => {
                container.appendChild(createTaskCard(task, true));
            });
        }

        async function completeTask(taskId) {
            try {
                const response = await fetch(`/api/tasks/${taskId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status: 'done' })
                });
                const result = await response.json();
                if (result.ok) {
                    loadTodayTasks();
                    loadBacklogTasks();
                } else {
                    alert('Error: ' + result.error);
                }
            } catch (error) {
                alert('Error: ' + error);
            }
        }

        async function promoteTask(taskId) {
            try {
                const response = await fetch(`/api/tasks/${taskId}/move_to_next_up`, { method: 'PUT' });
                const result = await response.json();
                if (result.ok) {
                    loadTodayTasks();
                    loadBacklogTasks();
                } else {
                    alert('Error: ' + result.error);
                }
            } catch (error) {
                alert('Error: ' + error);
            }
        }

        async function updateTaskStatus(taskId, status) {
            try {
                const response = await fetch(`/api/tasks/${taskId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status })
                });
                const result = await response.json();
                if (result.ok) {
                    loadTodayTasks();
                    loadBacklogTasks();
                } else {
                    alert('Error: ' + result.error);
                }
            } catch (error) {
                alert('Error updating task: ' + error);
            }
        }

        async function deleteTask(taskId) {
            if (!confirm('Delete this task?')) return;
            try {
                const response = await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
                const result = await response.json();
                if (result.ok) {
                    loadTodayTasks();
                    loadBacklogTasks();
                } else {
                    alert('Error: ' + result.error);
                }
            } catch (error) {
                alert('Error deleting task: ' + error);
            }
        }

        function toggleTaskComplete(taskId, checked) {
            if (checked) {
                completeTask(taskId);
            }
        }

        function showDeferDialog(taskId) {
            const date = prompt('Defer until (YYYY-MM-DD):');
            if (date) {
                deferTask(taskId, date);
            }
        }

        async function deferTask(taskId, deferUntil) {
            try {
                const response = await fetch(`/api/tasks/${taskId}/defer`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ defer_until: deferUntil })
                });
                const result = await response.json();
                if (result.ok) {
                    loadTodayTasks();
                } else {
                    alert('Error: ' + result.error);
                }
            } catch (error) {
                alert('Error deferring task: ' + error);
            }
        }

        document.getElementById('backlog-search').addEventListener('input', (e) => {
            renderBacklogTasks(e.target.value);
        });

        function openAddTaskModal() {
            document.getElementById('addTaskModal').classList.add('show');
            document.getElementById('addTaskModal').style.display = 'flex';
            document.getElementById('task-title').focus();
        }

        function closeAddTaskModal() {
            document.getElementById('addTaskModal').classList.remove('show');
            document.getElementById('addTaskModal').style.display = 'none';
            document.getElementById('task-title').value = '';
            document.getElementById('task-description').value = '';
            document.getElementById('task-priority').value = '0';
            document.getElementById('task-project').value = '';
            document.getElementById('task-due-date').value = '';
        }

        async function submitAddTask(e) {
            e.preventDefault();

            const title = document.getElementById('task-title').value;
            const description = document.getElementById('task-description').value;
            const priority = parseInt(document.getElementById('task-priority').value);
            const project = document.getElementById('task-project').value;
            const dueDate = document.getElementById('task-due-date').value;

            try {
                const response = await fetch('/api/tasks/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title,
                        description: description || null,
                        priority,
                        project: project || null,
                        due_date: dueDate || null
                    })
                });

                const result = await response.json();
                if (result.ok || result.task_id) {
                    closeAddTaskModal();
                    loadTodayTasks();
                    loadBacklogTasks();
                } else {
                    alert('Error: ' + (result.error || 'Failed to create task'));
                }
            } catch (error) {
                alert('Error creating task: ' + error);
            }
        }

        window.onclick = (event) => {
            const modal = document.getElementById('addTaskModal');
            if (event.target === modal) {
                closeAddTaskModal();
            }
        };

        // Initial load
        loadTodayTasks();
        loadBacklogTasks();

        // Refresh every 30 seconds
        setInterval(() => {
            loadTodayTasks();
            loadBacklogTasks();
        }, 30000);
    </script>
    '''

    full_html = page_content + modal_html + scripts
    return render_html_page("Tasks", full_html)


TASKS_PAGE_HTML = get_tasks_html()
