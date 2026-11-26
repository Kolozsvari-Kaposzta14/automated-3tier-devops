import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from '../src/App';

// Mock network calls so UI tests do not require PostgreSQL or a live backend.
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('three-stage task board', () => {
  it('shows a task in its saved column', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [
      { id: 1, title: 'Write tests', description: '', status: 'in_progress', created_at: new Date().toISOString() },
    ] }));
    render(<App />);
    expect(await screen.findByText('Write tests')).toBeInTheDocument();
    expect(screen.getByLabelText('Status for Write tests')).toHaveValue('in_progress');
  });

  it('creates a task in To do', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => [] })
      .mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({
        id: 2, title: 'New task', description: '', status: 'todo', created_at: new Date().toISOString(),
      }) });
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'New task' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add task' }));
    await waitFor(() => expect(screen.getByText('New task')).toBeInTheDocument());
    expect(screen.getByLabelText('Status for New task')).toHaveValue('todo');
  });

  it('moves a task to Done using PATCH', async () => {
    const task = { id: 3, title: 'Ship release', description: '', status: 'todo', created_at: new Date().toISOString() };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => [task] })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ ...task, status: 'done' }) });
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    const selector = await screen.findByLabelText('Status for Ship release');
    fireEvent.change(selector, { target: { value: 'done' } });
    await waitFor(() => expect(screen.getByLabelText('Status for Ship release')).toHaveValue('done'));
    expect(fetchMock).toHaveBeenCalledWith('/api/tasks/3', expect.objectContaining({
      method: 'PATCH', body: JSON.stringify({ status: 'done' }),
    }));
  });
});
