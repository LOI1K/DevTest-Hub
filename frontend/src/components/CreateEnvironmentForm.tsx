import { useState, type FormEvent } from "react";
import type { Environment } from "../types/environment";

type Props = {
  token: string;
  onCreated: (environment: Environment) => void;
};

function CreateEnvironmentForm({ token, onCreated }: Props) {
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setError("");
    setSuccess("");
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
          template: "nginx",
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
        placeholder="my-nginx-environment"
        pattern="[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
        minLength={3}
        maxLength={40}
        required
      />

      <p className="environment-hint">
        Используйте строчные латинские буквы, цифры и дефисы.
      </p>

      <p>
        Шаблон: <strong>nginx</strong>
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
