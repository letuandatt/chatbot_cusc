import axios from 'axios'

const BASE = 'http://localhost:8000'

export const api = axios.create({
  baseURL: BASE,
  timeout: 120000
})

// Sessions
export const listSessions = (limit = 50) => api.get(`/sessions?limit=${limit}`).then(r => r.data)
export const viewSession = (sessionId) => api.get(`/session/${sessionId}`).then(r => r.data)
export const createSession = () => api.post('/session/new').then(r => r.data)
export const deleteSession = (sessionId) => api.delete(`/session/${sessionId}/delete`).then(r => r.data)
export const deleteAllSessions = () => api.delete('/sessions/all').then(r => r.data)
export const renameSession = (sessionId, newName) => {
  return api.put(`/session/${sessionId}/rename`, { new_name: newName }) // Gửi new_name trong body
    .then(r => r.data);
}

