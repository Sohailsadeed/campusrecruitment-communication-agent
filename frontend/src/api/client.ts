import axios from "axios";

const baseURL =
  (import.meta.env.VITE_API_URL as string | undefined) ||
  "http://localhost:8000";

export const apiClient = axios.create({
  baseURL,
  timeout: 120000,
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("speakflow_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      localStorage.removeItem("speakflow_token");
    }
    return Promise.reject(error);
  }
);
