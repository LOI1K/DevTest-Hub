import { useState, type FormEvent } from "react";
import { Link } from "react-router";

type RegistrationResult = {
  id: number;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
};

function RegisterPage() {
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setError("");
    setSuccess("");
    setIsSubmitting(true);

    try {
      const response = await fetch("/api/v1/auth/register", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username,
          email,
          password,
        }),
      });

      if (response.status === 409) {
        setError("Логин или email уже зарегистрирован.");
        return;
      }

      if (!response.ok) {
        setError(`Ошибка регистрации: HTTP ${response.status}`);
        return;
      }

      const user: RegistrationResult = await response.json();

      setSuccess(`Пользователь ${user.username} зарегистрирован!`);
      setPassword("");
    } catch {
      setError("Нет соединения с сервером FastAPI.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="eyebrow">DevTest Hub</div>
        <h1>Создать аккаунт</h1>

        <p className="auth-description">
          Зарегистрируйтесь для управления тестовыми средами.
        </p>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label htmlFor="username">Логин</label>
          <input
            id="username"
            type="text"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            pattern="[a-z][a-z0-9_]*"
            minLength={3}
            maxLength={32}
            required
          />

          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            required
          />

          <label htmlFor="password">Пароль</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="new-password"
            minLength={12}
            maxLength={128}
            required
          />

          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          {success && (
            <p className="form-success" role="status">
              {success}
            </p>
          )}

          <button className="auth-submit" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Регистрация..." : "Зарегистрироваться"}
          </button>
        </form>

        <p className="auth-footer">
          Уже есть аккаунт? <Link to="/login">Войти</Link>
        </p>
      </section>
    </main>
  );
}

export default RegisterPage;
