import { useState, type FormEvent } from "react";
import type { Environment } from "../types/environment";

type Props = {
  environment: Environment;
  token: string;
  onUpdated: (environment: Environment) => void;
  onDeleted: (id: number) => void;
};

function EnvironmentCard({ environment, token, onUpdated }: Props) {
  const [isEditing, setIsEditing] = useState(false);
  const [name, setName] = useState(environment.name);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);

    try {
      const response = await fetch(`/api/v1/environments/${environment.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ name }),
      });

      if (!response.ok) {
        throw new Error(
          response.status === 422
            ? "Некорректное название среды."
            : `Ошибка изменения: HTTP ${response.status}`,
        );
      }

      const updated: Environment = await response.json();

      onUpdated(updated);
      setName(updated.name);
      setIsEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Неизвестная ошибка.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDelete() {
    if (environment.status === "deleting") return;

    const confirmed = window.confirm(`Удалить среду «${environment.name}»?`);

    if (!confirmed) return;

    setError("");
    setIsSubmitting(true);

    try {
      const response = await fetch(`/api/v1/environments/${environment.id}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (response.status !== 202) {
        throw new Error(`Ошибка удаления: HTTP ${response.status}`);
      }

      const updated: Environment = await response.json();

      onUpdated(updated);
      setIsEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Неизвестная ошибка.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <article className="card">
      <h3>{environment.name}</h3>

      <p>Шаблон: {environment.template}</p>
      <p>Статус: {environment.status}</p>
      <p>ID: {environment.id}</p>

      {environment.status === "running" && environment.host_port != null && (
        <div>
          <p>Адрес: http://127.0.0.1:{environment.host_port}</p>

          <a
            className="environment-open-button"
            href={`http://127.0.0.1:${environment.host_port}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            Открыть среду
          </a>
        </div>
      )}

      {environment.status === "deleting" ? (
      <p role="status">
        Удаление запрошено. Ожидается обработка Docker Worker.
      </p>
    ) : isEditing ? (
        <form className="environment-edit-form" onSubmit={handleUpdate}>
          <label htmlFor={`edit-${environment.id}`}>Новое название</label>

          <input
            id={`edit-${environment.id}`}
            value={name}
            onChange={(event) => setName(event.target.value)}
            pattern="[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
            minLength={3}
            maxLength={40}
            required
          />

          <div className="environment-actions">
            <button type="submit" disabled={isSubmitting}>
              Сохранить
            </button>

            <button
              type="button"
              disabled={isSubmitting}
              onClick={() => {
                setName(environment.name);
                setError("");
                setIsEditing(false);
              }}
            >
              Отмена
            </button>
          </div>
        </form>
      ) : (
        <div className="environment-actions">
          <button
            type="button"
            disabled={isSubmitting}
            onClick={() => setIsEditing(true)}
          >
            Изменить
          </button>

          <button
            type="button"
            className="danger-button"
            disabled={isSubmitting}
            onClick={handleDelete}
          >
            Удалить
          </button>
        </div>
      )}

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </article>
  );
}

export default EnvironmentCard;
