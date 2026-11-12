import { useState, type FormEvent } from "react";
import type { Environment } from "../types/environment";

type Props = {
  token: string;
  onCreated: (environment: Environment) => void;
};

type EnvironmentTemplate = "nginx" | "fastapi-postgres";

function CreateEnvironmentForm({ token, onCreated }: Props) {
  const [name, setName] = useState("");
  const [template, setTemplate] = useState<EnvironmentTemplate>("nginx");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Пока новый Worker не прошёл интеграционные тесты,
  // шаблон FastAPI + PostgreSQL недоступен в интерфейсе.
  const fastapiAvailable =
    import.meta.env.VITE_ENABLE_FASTAPI_POSTGRES === "true";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setError("");
    setSuccess("");

    if (template === "fastapi-postgres" && !fastapiAvailable) {
      setError("Шаблон FastAPI + PostgreSQL пока недоступен.");
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await fetch("/api/v1/environments", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name,
          template,
        }),
      });

      if (response.status === 401) {
        throw new Error("Сессия истекла. Войдите повторно.");
      }

      if (response.status === 422) {
        throw new Error("Проверьте правильность имени среды.");
      }

      if (!response.ok) {
        throw new Error(`Ошибка создания: HTTP ${response.status}`);
      }

      const created: Environment = await response.json();

      onCreated(created);
      setName("");
      setTemplate("nginx");

      setSuccess(`Среда «${created.name}» создана.`);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Не удалось подключиться к серверу.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className="auth-form environment-create-form" onSubmit={handleSubmit}>
      <h3>Создать тестовую среду</h3>

      <label htmlFor="environment-name">Название среды</label>

      <input
        id="environment-name"
        type="text"
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder={
          template === "nginx"
            ? "my-nginx-environment"
            : "my-fastapi-environment"
        }
        pattern="[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
        minLength={3}
        maxLength={40}
        required
      />

      <p className="environment-hint">
        Используйте строчные латинские буквы, цифры и дефисы.
      </p>

      <label htmlFor="environment-template">Шаблон среды</label>

      <select
        id="environment-template"
        className="environment-template-select"
        value={template}
        onChange={(event) =>
          setTemplate(event.target.value as EnvironmentTemplate)
        }
        disabled={isSubmitting}
      >
        <option value="nginx">Nginx — веб-сервер</option>

        <option value="fastapi-postgres" disabled={!fastapiAvailable}>
          FastAPI + PostgreSQL
          {!fastapiAvailable ? " (пока недоступен)" : ""}
        </option>
      </select>

      <p className="environment-hint">
        {template === "nginx"
          ? "Простая тестовая среда с веб-сервером Nginx."
          : "API, PostgreSQL, изолированная сеть и постоянное хранилище."}
      </p>

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
        {isSubmitting ? "Создание..." : "Создать среду"}
      </button>
    </form>
  );
}

export default CreateEnvironmentForm;
