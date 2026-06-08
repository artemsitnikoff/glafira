import axios, { AxiosError } from 'axios';
import type { InternalAxiosRequestConfig } from 'axios';
import { useAuthStore } from '@/store/authStore';
import type { ApiError } from './aliases';

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  withCredentials: true,
});

export const client = api; // Alias for consistency

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

interface RetriableConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

// Дедупликация refresh: при «буре» одновременных 401 (поллинг smart + параллельные
// запросы страницы) делаем ОДИН /auth/refresh, все ждут его. Иначе N конкурентных
// refresh → гонка и ложный logout, если хоть один из них транзиентно упадёт.
let refreshPromise: Promise<string> | null = null;

function runRefresh(): Promise<string> {
  if (!refreshPromise) {
    refreshPromise = api
      .post('/auth/refresh')
      .then((res) => {
        const token = (res.data as { access_token: string }).access_token;
        useAuthStore.getState().setToken(token);
        return token;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetriableConfig | undefined;
    const isRefreshCall = original?.url?.endsWith('/auth/refresh');

    if (error.response?.status === 401 && original && !original._retry && !isRefreshCall) {
      original._retry = true;
      try {
        const newToken = await runRefresh();
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      } catch (refreshError) {
        useAuthStore.getState().logout();
        window.location.href = '/login';
        return Promise.reject(normalizeApiError(refreshError));
      }
    }

    return Promise.reject(normalizeApiError(error));
  }
);

function normalizeApiError(error: unknown): ApiError {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data;
    if (data && typeof data === 'object' && 'error' in data) {
      return data as ApiError;
    }
    return {
      error: {
        code: error.code === 'ERR_NETWORK' ? 'NETWORK_ERROR' : 'UNKNOWN_ERROR',
        message: error.message ?? 'Unknown error',
        details: null,
      },
    };
  }
  return {
    error: { code: 'UNKNOWN_ERROR', message: String(error), details: null },
  };
}