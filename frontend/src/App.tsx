import { useEffect, useState, type FormEvent } from 'react';
import { taskApi } from './api';
import type { Task, TaskStatus } from './types';
import './style.css';

// Use one canonical list of stages for the board and the status selector.
const columns: { status: TaskStatus; label: string }[] = [
  { status: 'todo', label: 'To do' },
  { status: 'in_progress', label: 'In progress' },
  { status: 'done', label: 'Done' },
];

export default function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  // Load existing records from the backend when the application opens.
  useEffect(() => {
    let active = true;
    taskApi.list().then(data => { if (active) setTasks(data); })
      .catch(() => { if (active) setError('Could not load tasks. Check the API.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  async function addTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    setError('');
    try {
      // Newly created tasks start in the To do column by backend default.
      const created = await taskApi.create(title.trim(), description.trim());
      setTasks(current => [created, ...current]);
      setTitle('');
      setDescription('');
    } catch { setError('Could not create task.'); }
    finally { setBusy(false); }
  }

  async function moveTask(task: Task, status: TaskStatus) {
    if (task.status === status) return;
    setError('');
    try {
      // Persist the transition before updating the board so UI and DB agree.
      const updated = await taskApi.update(task.id, { status });
      setTasks(current => current.map(item => item.id === task.id ? updated : item));
    } catch { setError('Could not move task.'); }
  }

  async function editTask(task: Task) {
    // Simple browser dialogs keep this initial implementation dependency-free.
    const nextTitle = window.prompt('Edit task title', task.title);
    if (nextTitle === null || !nextTitle.trim() || nextTitle.trim().length > 120) return;
    const nextDescription = window.prompt('Edit task description', task.description);
    if (nextDescription === null || nextDescription.length > 1000) return;
    setError('');
    try {
      const updated = await taskApi.update(task.id, { title: nextTitle.trim(), description: nextDescription });
      setTasks(current => current.map(item => item.id === task.id ? updated : item));
    } catch { setError('Could not edit task.'); }
  }

  async function removeTask(id: number) {
    // Ask before a destructive operation.
    if (!window.confirm('Delete this task permanently?')) return;
    setError('');
    try {
      await taskApi.remove(id);
      setTasks(current => current.filter(item => item.id !== id));
    } catch { setError('Could not delete task.'); }
  }

  return (
    <main className="shell">
      <header>
        <p className="eyebrow">THREE-TIER DEVOPS DEMO</p>
        <h1>Task Manager</h1>
        <p>Track tasks across three stages. Every change is stored in the database.</p>
      </header>
      <section className="panel" aria-label="Create task">
        <h2>Add a task</h2>
        <form onSubmit={addTask}>
          <label htmlFor="title">Title</label>
          <input id="title" maxLength={120} value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. Validate CI pipeline" required />
          <label htmlFor="description">Description (optional)</label>
          <textarea id="description" maxLength={1000} value={description} onChange={e => setDescription(e.target.value)} rows={2} />
          <button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Add task'}</button>
        </form>
      </section>
      {error && <p className="error" role="alert">{error}</p>}
      {loading && <p role="status">Loading tasks…</p>}
      <section className="board" aria-label="Task board">
        {columns.map(column => {
          const visible = tasks.filter(task => task.status === column.status);
          return (
            <section className="board-column" key={column.status} aria-label={column.label}>
              <h2>{column.label} <span className="count">{visible.length}</span></h2>
              {visible.length === 0 && <p className="empty">No tasks here yet.</p>}
              {visible.map(task => (
                <article className="task-card" key={task.id}>
                  <h3>{task.title}</h3>
                  {task.description && <p>{task.description}</p>}
                  <label htmlFor={`status-${task.id}`}>Status</label>
                  <select id={`status-${task.id}`} aria-label={`Status for ${task.title}`} value={task.status} onChange={event => void moveTask(task, event.target.value as TaskStatus)}>
                    {columns.map(option => <option key={option.status} value={option.status}>{option.label}</option>)}
                  </select>
                  <div className="task-actions">
                    <button className="secondary" onClick={() => void editTask(task)} aria-label={`Edit ${task.title}`}>Edit</button>
                    <button className="danger" onClick={() => void removeTask(task.id)} aria-label={`Delete ${task.title}`}>Delete</button>
                  </div>
                </article>
              ))}
            </section>
          );
        })}
      </section>
    </main>
  );
}
