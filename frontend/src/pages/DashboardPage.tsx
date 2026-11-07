import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { useAuth } from "../auth/useAuth";
import CreateEnvironmentForm from "../components/CreateEnvironmentForm";
import type { Environment } from "../types/environment";
import EnvironmentCard from "../components/EnvironmentCard";

function DashboardPage() {
  const { session, logout } = useAuth();
  const navigate = useNavigate();

  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const token = session?.token;

  useEffect(() => {
    if (!token) return;

    const controller = new AbortController();
    let isLoading = false;

    async function loadEnvironments() {
      if (isLoading || controller.signal.aborted) return;

      isLoading = true;

      try {
        const response = await fetch("/api/v1/environments", {
          headers: {
            Authorization: `Bearer ${token}`,
          },
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(
            response.status === 401
              ? "Сессия истекла. Войдите повторно."
              : `Ошибка загрузки: HTTP ${response.status}`,
          );
        }

        const data: Environment[] = await response.json();

        if (!controller.signal.aborted) {
          setEnvironments(data);
          setError("");
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(
            err instanceof Error
              ? err.message
              : "Не удалось получить тестовые среды.",
          );
        }
      } finally {
        isLoading = false;

        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void loadEnvironments();

    const intervalId = window.setInterval(() => {
      void loadEnvironments();
    }, 5000);

    function refreshWhenVisible() {
      if (document.visibilityState === "visible") {
        void loadEnvironments();
      }
    }

    document.addEventListener("visibilitychange", refreshWhenVisible);
    window.addEventListener("focus", refreshWhenVisible);

    return () => {
      window.clearInterval(intervalId);

      document.removeEventListener(
        "visibilitychange",
        refreshWhenVisible,
      );

      window.removeEventListener("focus", refreshWhenVisible);

      controller.abort();
    };
  }, [token]);

  function handleCreated(environment: Environment) {
    setEnvironments((current) => [...current, environment]);
  }

  function handleUpdated(updated: Environment) {
    setEnvironments((current) =>
      current.map((environment) =>
        environment.id === updated.id ? updated : environment,
      ),
    );
  }

  function handleDeleted(id: number) {
    setEnvironments((current) =>
      current.filter((environment) => environment.id !== id),
    );
  }

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <main className="main">
      <div className="eyebrow">Личный кабинет</div>

      <h1>Добро пожаловать, {session?.user.username}!</h1>

      <p className="description">Управляйте своими тестовыми средами.</p>

      <section className="section">
        <h2>Ваш профиль</h2>
        <p>Email: {session?.user.email}</p>
        <p>Роль: {session?.user.role}</p>
      </section>

      <section className="section">
        <h2>Мои тестовые среды</h2>
        {token && (
          <CreateEnvironmentForm token={token} onCreated={handleCreated} />
        )}

        {loading ? (
          <p>Загрузка тестовых сред...</p>
        ) : error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : environments.length === 0 ? (
          <p className="description">У вас пока нет тестовых сред.</p>
        ) : (
          <div className="cards">
            {token &&
              environments.map((environment) => (
                <EnvironmentCard
                  key={environment.id}
                  environment={environment}
                  token={token}
                  onUpdated={handleUpdated}
                  onDeleted={handleDeleted}
                />
              ))}
          </div>
        )}
      </section>

      <button className="auth-submit" type="button" onClick={handleLogout}>
        Выйти из аккаунта
      </button>
    </main>
  );
}

export default DashboardPage;
