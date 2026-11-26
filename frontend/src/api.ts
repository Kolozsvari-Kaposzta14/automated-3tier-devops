import type { Task } from './types';

// Use relative /api paths so Vite's development proxy and future Nginx both work.
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });
  if (!response.ok) throw new Error(`API request failed (${response.status})`);
  // DELETE returns 204 No Content, which must not be parsed as JSON.
  return response.status === 204 ? (undefined as T) : (response.json() as Promise<T>);
}

export const taskApi = {
  list: () => request<Task[]>('/tasks'),
  create: (title: string, description: string) => request<Task>('/tasks', {
    method: 'POST', body: JSON.stringify({ title, description }),
  }),
  update: (id: number, changes: Partial<Pick<Task, 'title' | 'description' | 'status'>>) =>
    request<Task>(`/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(changes) }),
  remove: (id: number) => request<void>(`/tasks/${id}`, { method: 'DELETE' }),
};
