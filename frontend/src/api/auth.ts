import { apiClient } from "./client";

export interface UserOut {
  id: number;
  email: string;
  username: string;
  full_name?: string | null;
  resume_name?: string | null;
  created_at: string;
}

export interface Token {
  access_token: string;
  token_type: string;
  user: UserOut;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  username: string;
  full_name?: string;
  password: string;
}

export async function loginUser(payload: LoginPayload): Promise<Token> {
  const res = await apiClient.post<Token>("/api/auth/login", payload);
  return res.data;
}

export async function registerUser(payload: RegisterPayload): Promise<Token> {
  const res = await apiClient.post<Token>("/api/auth/register", payload);
  return res.data;
}

export async function getMe(): Promise<UserOut> {
  const res = await apiClient.get<UserOut>("/api/auth/me");
  return res.data;
}
