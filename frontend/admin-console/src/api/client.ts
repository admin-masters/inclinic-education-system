import axios from 'axios';

const baseURL = import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000';

export const api = axios.create({
  baseURL: `${baseURL}/api/`,      // <—— root of the Django API
  withCredentials: true,           // send session cookie
});