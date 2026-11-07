import { useState, type ReactNode } from "react";
import { AuthContext, type AuthSession, type CurrentUser } from "./AuthContext";

type Props = {
  children: ReactNode;
};

function AuthProvider({ children }: Props) {
  const [session, setSession] = useState<AuthSession | null>(null);

  async function login(username: string, password: string) {
    const response = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({ username, password }),
    });

    if (response.status === 401) {
      throw new Error("Неверный логин или пароль.");
    }

    if (!response.ok) {
      throw new Error(`Ошибка входа: HTTP ${response.status}`);
    }

    const data: { access_token: string } = await response.json();

    const profileResponse = await fetch("/api/v1/users/me", {
      headers: {
        Authorization: `Bearer ${data.access_token}`,
      },
    });

    if (!profileResponse.ok) {
      throw new Error("Не удалось получить профиль пользователя.");
    }

    const user: CurrentUser = await profileResponse.json();

    setSession({
      token: data.access_token,
      user,
    });
  }

  function logout() {
    setSession(null);
  }

  return (
    <AuthContext.Provider value={{ session, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export default AuthProvider;
