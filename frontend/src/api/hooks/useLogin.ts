import { useMutation } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api } from '../client';
import { useAuthStore } from '@/store/authStore';
import type { UserMe } from '../aliases';

interface LoginPayload {
  email: string;
  password: string;
}

interface LoginResponse {
  access_token: string;
  token_type: string;
}

export function useLogin() {
  const navigate = useNavigate();
  const { setAuth } = useAuthStore();

  return useMutation({
    mutationFn: async (payload: LoginPayload) => {
      // Сначала логинимся
      const loginResponse = await api.post<LoginResponse>('/auth/login', payload);

      // Затем сразу подтягиваем профиль с токеном
      const meResponse = await api.get<UserMe>('/auth/me', {
        headers: {
          Authorization: `Bearer ${loginResponse.data.access_token}`,
        },
      });

      return {
        token: loginResponse.data.access_token,
        user: meResponse.data,
      };
    },
    onSuccess: ({ token, user }) => {
      setAuth(token, user);
      navigate('/home', { replace: true });
    },
  });
}