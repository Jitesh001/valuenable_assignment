import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const original = err.config;
    if (err.response?.status === 401 && !original._retried) {
      original._retried = true;
      const refresh = localStorage.getItem("refresh");
      if (refresh) {
        try {
          const r = await axios.post("/api/auth/refresh/", { refresh });
          localStorage.setItem("access", r.data.access);
          if (r.data.refresh) localStorage.setItem("refresh", r.data.refresh);
          original.headers.Authorization = `Bearer ${r.data.access}`;
          return api(original);
        } catch {
          localStorage.clear();
        }
      }
    }
    return Promise.reject(err);
  }
);

export default api;
