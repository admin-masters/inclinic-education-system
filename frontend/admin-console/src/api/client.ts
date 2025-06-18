import axios from "axios";

export const api = axios.create({
  baseURL:
    import.meta.env.VITE_BACKEND_URL        // ← already in your .env
    || "https://new.cpdinclinic.co.in",     // 🡒 prod default
  withCredentials: true,                    // keeps Django session-cookie
});
