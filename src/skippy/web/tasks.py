import logging
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

logger = logging.getLogger("skippy")

router = APIRouter()


@router.get("/tasks", response_class=HTMLResponse)
async def tasks_page():
    """Serve the tasks management page."""
    return TASKS_PAGE_HTML


TASKS_PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Tasks</title>
    <style>
        * {
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 0;
            background: #f5f5f5;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
        }

        h1 {
            color: #333;
            margin: 0;
            font-size: 2em;
        }

        .header-actions {
            display: flex;
            gap: 15px;
            align-items: center;
        }

        .add-btn {
            background: #82aaff;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 500;
            font-size: 0.95em;
            transition: all 0.2s;
        }

        .add-btn:hover {
            background: #6a8dd9;
            box-shadow: 0 2px 8px rgba(130, 170, 255, 0.3);
        }

        .back-link {
            color: #82aaff;
            text-decoration: none;
            font-weight: 500;
        }

        .back-link:hover {
            text-decoration: underline;
        }

        /* Modal Styles */
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.5);
        }

        .modal.show {
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .modal-content {
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            width: 90%;
            max-width: 500px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
        }

        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            border-bottom: 1px solid #eee;
            padding-bottom: 15px;
        }

        .modal-header h2 {
            margin: 0;
            color: #333;
        }

        .close-btn {
            background: none;
            border: none;
            font-size: 1.5em;
            cursor: pointer;
            color: #999;
        }

        .close-btn:hover {
            color: #333;
        }

        .form-group {
            margin-bottom: 15px;
        }

        .form-group label {
            display: block;
            margin-bottom: 5px;
            font-weight: 500;
            color: #333;
            font-size: 0.9em;
        }

        .form-group input,
        .form-group textarea,
        .form-group select {
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 0.95em;
            font-family: inherit;
        }

        .form-group textarea {
            resize: vertical;
            min-height: 80px;
        }

        .form-group input:focus,
        .form-group textarea:focus,
        .form-group select:focus {
            outline: none;
            border-color: #82aaff;
            box-shadow: 0 0 0 3px rgba(130, 170, 255, 0.1);
        }

        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }

        .modal-actions {
            display: flex;
            gap: 10px;
            justify-content: flex-end;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #eee;
        }

        .modal-actions button {
            padding: 10px 20px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 500;
            transition: all 0.2s;
        }

        .modal-actions .cancel-btn {
            background: #f0f0f0;
            color: #333;
        }

        .modal-actions .cancel-btn:hover {
            background: #e0e0e0;
        }

        .modal-actions .submit-btn {
            background: #82aaff;
            color: white;
        }

        .modal-actions .submit-btn:hover {
            background: #6a8dd9;
        }

        .modal-actions .submit-btn:disabled {
            background: #ccc;
            cursor: not-allowed;
        }

        .two-column {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 20px;
        }

        @media (max-width: 1024px) {
            .two-column {
                grid-template-columns: 1fr;
            }
        }

        .panel {
            background: white;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            padding: 20px;
            max-height: 80vh;
            overflow-y: auto;
        }

        .panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            border-bottom: 2px solid #f0f0f0;
            padding-bottom: 15px;
        }

        .panel-title {
            font-size: 1.3em;
            font-weight: 600;
            color: #333;
            margin: 0;
        }

        .panel-count {
            background: #e3f2fd;
            color: #1976d2;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.9em;
            font-weight: 500;
        }

        .filters {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }

        .filter-btn {
            background: #f0f0f0;
            border: 1px solid #ddd;
            padding: 8px 16px;
            border-radius: 20px;
            cursor: pointer;
            font-size: 0.9em;
            transition: all 0.2s;
        }

        .filter-btn.active {
            background: #82aaff;
            color: white;
            border-color: #82aaff;
        }

        .filter-btn:hover {
            border-color: #999;
        }

        .task-card {
            background: #fafafa;
            border: 1px solid #eee;
            border-radius: 6px;
            padding: 15px;
            margin-bottom: 12px;
            cursor: pointer;
            transition: all 0.2s;
            border-left: 4px solid #82aaff;
        }

        .task-card:hover {
            background: #f5f5f5;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }

        .task-card.expanded {
            background: #f9f9f9;
        }

        .task-checkbox {
            width: 20px;
            height: 20px;
            cursor: pointer;
            margin-right: 12px;
            vertical-align: middle;
        }

        .task-header {
            display: flex;
            align-items: center;
            margin-bottom: 8px;
        }

        .task-title {
            flex: 1;
            font-weight: 500;
            color: #333;
            font-size: 1em;
        }

        .task-badges {
            display: flex;
            gap: 8px;
            align-items: center;
        }

        .badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 10px;
            font-size: 0.75em;
            font-weight: 500;
            white-space: nowrap;
        }

        .badge.priority-urgent {
            background: #ffebee;
            color: #c62828;
        }

        .badge.priority-high {
            background: #fff3e0;
            color: #e65100;
        }

        .badge.priority-medium {
            background: #e3f2fd;
            color: #1565c0;
        }

        .badge.priority-low {
            background: #f3e5f5;
            color: #6a1b9a;
        }

        .badge.project {
            background: #e8f5e9;
            color: #2e7d32;
        }

        .badge.status {
            background: #eceff1;
            color: #546e7a;
        }

        .task-meta {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.85em;
            color: #666;
            margin-top: 8px;
        }

        .task-due {
            display: flex;
            align-items: center;
            gap: 4px;
        }

        .task-due.overdue {
            color: #d32f2f;
            font-weight: 600;
        }

        .task-due.due-today {
            color: #f57c00;
            font-weight: 600;
        }

        .task-details {
            display: none;
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #eee;
        }

        .task-card.expanded .task-details {
            display: block;
        }

        .task-description {
            color: #666;
            font-size: 0.9em;
            margin-bottom: 12px;
            line-height: 1.4;
        }

        .task-actions {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }

        .action-btn {
            padding: 6px 12px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.85em;
            font-weight: 500;
            transition: all 0.2s;
        }

        .action-btn.complete {
            background: #4caf50;
            color: white;
        }

        .action-btn.complete:hover {
            background: #45a049;
        }

        .action-btn.promote {
            background: #2196f3;
            color: white;
        }

        .action-btn.promote:hover {
            background: #0b7dda;
        }

        .action-btn.defer {
            background: #ff9800;
            color: white;
        }

        .action-btn.defer:hover {
            background: #e68900;
        }

        .action-btn.delete {
            background: #f44336;
            color: white;
        }

        .action-btn.delete:hover {
            background: #da190b;
        }

        .empty-state {
            text-align: center;
            color: #999;
            padding: 40px 20px;
        }

        .empty-state-icon {
            font-size: 2em;
            margin-bottom: 10px;
        }

        .search-input {
            width: 100%;
            padding: 10px 15px;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 0.95em;
            margin-bottom: 15px;
        }

        .search-input:focus {
            outline: none;
            border-color: #82aaff;
            box-shadow: 0 0 0 3px rgba(130, 170, 255, 0.1);
        }

        .loading {
            text-align: center;
            color: #999;
            padding: 20px;
        }

        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid #f3f3f3;
            border-top: 3px solid #82aaff;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>✓ Tasks</h1>
            <div class="header-actions">
                <button class="add-btn" onclick="openAddTaskModal()">+ Add Task</button>
                <a href="/" class="back-link">← Back to Dashboard</a>
            </div>
        </header>

        <div class="two-column">
            <!-- TODAY PANEL -->
            <div class="panel">
                <div class="panel-header">
                    <h2 class="panel-title">📋 Today</h2>
                    <div class="panel-count" id="today-count">0</div>
                </div>

                <div class="filters">
                    <button class="filter-btn active" onclick="filterTodayTasks('all')">All</button>
                    <button class="filter-btn" onclick="filterTodayTasks('due-today')">Due Today</button>
                    <button class="filter-btn" onclick="filterTodayTasks('in-progress')">In Progress</button>
                    <button class="filter-btn" onclick="filterTodayTasks('blocked')">Blocked</button>
                </div>

                <div id="today-tasks" class="loading">
                    <div class="spinner"></div> Loading tasks...
                </div>
            </div>

            <!-- BACKLOG PANEL -->
            <div class="panel">
                <div class="panel-header">
                    <h2 class="panel-title">📚 Backlog</h2>
                    <div class="panel-count" id="backlog-count">0</div>
                </div>

                <input type="text" class="search-input" id="backlog-search" placeholder="Search backlog...">

                <div id="backlog-tasks" class="loading">
                    <div class="spinner"></div> Loading backlog...
                </div>
            </div>
        </div>
    </div>

    <!-- Add Task Modal -->
    <div id="addTaskModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>Create New Task</h2>
                <button class="close-btn" onclick="closeAddTaskModal()">✕</button>
            </div>

            <form onsubmit="submitAddTask(event)">
                <div class="form-group">
                    <label for="task-title">Task Title *</label>
                    <input type="text" id="task-title" name="title" required placeholder="What needs to be done?">
                </div>

                <div class="form-group">
                    <label for="task-description">Description</label>
                    <textarea id="task-description" name="description" placeholder="Add details about the task..."></textarea>
                </div>

                <div class="form-row">
                    <div class="form-group">
                        <label for="task-priority">Priority</label>
                        <select id="task-priority" name="priority">
                            <option value="0">None</option>
                            <option value="1">Low</option>
                            <option value="2">Medium</option>
                            <option value="3">High</option>
                            <option value="4">Urgent</option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label for="task-project">Project</label>
                        <input type="text" id="task-project" name="project" placeholder="Optional project name">
                    </div>
                </div>

                <div class="form-group">
                    <label for="task-due-date">Due Date</label>
                    <input type="date" id="task-due-date" name="due_date">
                </div>

                <div class="modal-actions">
                    <button type="button" class="cancel-btn" onclick="closeAddTaskModal()">Cancel</button>
                    <button type="submit" class="submit-btn">Create Task</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        let allTodayTasks = [];
        let allBacklogTasks = [];
        let currentTodayFilter = 'all';

        const priorityLabels = {
            0: 'None',
            1: 'Low',
            2: 'Medium',
            3: 'High',
            4: 'Urgent'
        };

        const statusLabels = {
            'inbox': 'Inbox',
            'next_up': 'Next Up',
            'in_progress': 'In Progress',
            'blocked': 'Blocked',
            'waiting': 'Waiting',
            'done': 'Done'
        };

        function formatDate(dateStr) {
            if (!dateStr) return '';
            const date = new Date(dateStr);
            const now = new Date();
            const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            const taskDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
            const diffMs = taskDate - today;
            const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

            if (diffDays === 0) return '📅 Today';
            if (diffDays === 1) return '📅 Tomorrow';
            if (diffDays < 0) return `📅 Overdue by ${Math.abs(diffDays)}d`;
            if (diffDays <= 3) return `📅 In ${diffDays}d`;
            return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        }

        function getPriorityBadge(priority) {
            const classes = ['priority-none', 'priority-low', 'priority-medium', 'priority-high', 'priority-urgent'];
            return `<span class="badge ${classes[priority] || 'priority-none'}">${priorityLabels[priority] || 'None'}</span>`;
        }

        function formatDueDate(dueDate) {
            if (!dueDate) return '';
            const date = new Date(dueDate);
            const now = new Date();
            const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            const taskDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
            const diffMs = taskDate - today;
            const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

            if (diffDays < 0) return 'overdue';
            if (diffDays === 0) return 'due-today';
            if (diffDays <= 3) return 'due-soon';
            return 'due-later';
        }

        function createTaskCard(task, isBacklog = false) {
            const dueClass = formatDueDate(task.due_date);
            const dueDateStr = formatDate(task.due_date);

            let badgesHtml = '';
            if (task.priority > 0) {
                badgesHtml += getPriorityBadge(task.priority);
            }
            if (task.project) {
                badgesHtml += `<span class="badge project">${task.project}</span>`;
            }
            if (!isBacklog && task.status !== 'inbox') {
                badgesHtml += `<span class="badge status">${statusLabels[task.status] || task.status}</span>`;
            }

            const card = document.createElement('div');
            card.className = 'task-card';
            card.innerHTML = `
                <div class="task-header">
                    <input type="checkbox" class="task-checkbox" onchange="toggleTaskComplete(${task.task_id}, this.checked)">
                    <span class="task-title">${task.title}</span>
                </div>
                <div class="task-badges">
                    ${badgesHtml}
                </div>
                ${dueDateStr ? `<div class="task-meta"><span class="task-due ${dueClass}">${dueDateStr}</span></div>` : ''}
                <div class="task-details">
                    ${task.description ? `<div class="task-description">${task.description}</div>` : ''}
                    <div class="task-actions">
                        ${!isBacklog ? `<button class="action-btn complete" onclick="completeTask(${task.task_id})">✓ Complete</button>` : ''}
                        ${isBacklog ? `<button class="action-btn promote" onclick="promoteTask(${task.task_id})">↑ Promote to Active</button>` : `<button class="action-btn defer" onclick="showDeferDialog(${task.task_id})">⏸ Defer</button>`}
                        ${!isBacklog && task.status !== 'blocked' ? `<button class="action-btn" style="background: #9c27b0; color: white;" onclick="updateTaskStatus(${task.task_id}, 'blocked')">🚫 Block</button>` : ''}
                        <button class="action-btn delete" onclick="deleteTask(${task.task_id})">🗑 Delete</button>
                    </div>
                </div>
            `;

            card.onclick = (e) => {
                if (e.target.tagName !== 'BUTTON' && e.target.tagName !== 'INPUT') {
                    card.classList.toggle('expanded');
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
                document.getElementById('today-tasks').innerHTML = '<div class="empty-state"><div class="empty-state-icon">❌</div><p>Error loading tasks</p></div>';
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
                document.getElementById('backlog-tasks').innerHTML = '<div class="empty-state"><div class="empty-state-icon">❌</div><p>Error loading backlog</p></div>';
            }
        }

        function filterTodayTasks(filter) {
            currentTodayFilter = filter;

            // Update button states (only if called from event)
            if (event && event.target) {
                document.querySelectorAll('.filters .filter-btn').forEach(btn => {
                    btn.classList.remove('active');
                });
                event.target.classList.add('active');
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
                container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">✨</div><p>No tasks today!</p></div>';
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
                container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📭</div><p>No backlog items</p></div>';
                return;
            }

            container.innerHTML = '';
            filtered.forEach(task => {
                container.appendChild(createTaskCard(task, true));
            });
        }

        async function completeTask(taskId) {
            try {
                const response = await fetch(`/api/tasks/${taskId}/complete`, { method: 'PUT' });
                const result = await response.json();
                if (result.ok) {
                    loadTodayTasks();
                } else {
                    alert('Error: ' + result.error);
                }
            } catch (error) {
                alert('Error completing task: ' + error);
            }
        }

        async function promoteTask(taskId) {
            try {
                const response = await fetch(`/api/tasks/${taskId}/promote`, { method: 'PUT' });
                const result = await response.json();
                if (result.ok) {
                    loadBacklogTasks();
                    loadTodayTasks();
                } else {
                    alert('Error: ' + result.error);
                }
            } catch (error) {
                alert('Error promoting task: ' + error);
            }
        }

        async function updateTaskStatus(taskId, newStatus) {
            try {
                const response = await fetch(`/api/tasks/${taskId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status: newStatus })
                });
                const result = await response.json();
                if (result.ok) {
                    loadTodayTasks();
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

        // Search backlog tasks
        document.getElementById('backlog-search').addEventListener('input', (e) => {
            renderBacklogTasks(e.target.value);
        });

        // Initial load
        loadTodayTasks();
        loadBacklogTasks();

        // Refresh every 30 seconds
        setInterval(() => {
            loadTodayTasks();
            loadBacklogTasks();
        }, 30000);

        // Modal functions
        function openAddTaskModal() {
            document.getElementById('addTaskModal').classList.add('show');
            document.getElementById('task-title').focus();
        }

        function closeAddTaskModal() {
            document.getElementById('addTaskModal').classList.remove('show');
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

        // Close modal when clicking outside
        window.onclick = (event) => {
            const modal = document.getElementById('addTaskModal');
            if (event.target === modal) {
                closeAddTaskModal();
            }
        };
    </script>
</body>
</html>
"""
