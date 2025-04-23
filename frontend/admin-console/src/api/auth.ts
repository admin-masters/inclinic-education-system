// src/api/auth.ts
import { api } from './client';
import { getCookie } from '../api/cookies';
export const logout = async () => {
  await api.post('/auth/logout/', null, {
    headers: { 'X-CSRFToken': getCookie('csrftoken') || '' },
  });
  window.location.href = '/';           // or navigate('/login')
};