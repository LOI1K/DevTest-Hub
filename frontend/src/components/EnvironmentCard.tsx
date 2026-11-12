import { useState, type FormEvent } from "react";
import type { Environment } from "../types/environment";

type Props = {
  environment: Environment;
  token: string;
  onUpdated: (environment: Environment) => void;
  onDeleted: (id: number) => void;
};

const statusLabels: Record<string, string> = {
  pending: "Ожидает создания",
  deploying: "Развёртывается",
  running: "Работает",
  stopped: "Остановлена",
  failed: "Ошибка",
  deleting: "Удаляется",
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
    if (
      environment.status === "deleting" ||
      environment.status === "deploying"
    ) {
      return;
    }

    const isFastapiPostgres = environment.template === "fastapi-postgres";

    setError("");

    const confirmed = window.confirm(
      isFastapiPostgres
        ? `Удалить среду «${environment.name}»?\n\n` +
            "ВНИМАНИЕ! Будут безвозвратно удалены " +
            "контейнеры FastAPI и PostgreSQL, " +
            "а также том со всеми данными базы."
        : `Удалить среду «${environment.name}»?`,
    );

    if (!confirmed) {
      return;
    }

    // Для среды с постоянным хранилищем
    // требуем дополнительное подтверждение.
    if (isFastapiPostgres) {
      const enteredName = window.prompt(
        "Для подтверждения безвозвратного удаления " +
          "введите точное название среды:",
        "",
      );

      if (enteredName === null) {
        return;
      }

      if (enteredName !== environment.name) {
        setError("Удаление отменено: имя среды не совпадает.");
        return;
      }
    }

    setIsSubmitting(true);

    try {
      const url = isFastapiPostgres
        ? `/api/v1/environments/${environment.id}?delete_volume=true`
        : `/api/v1/environments/${environment.id}`;

      const response = await fetch(url, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (response.status !== 202) {
        throw new Error(
          response.status === 409
            ? "Сейчас удалить среду нельзя."
            : `Ошибка удаления: HTTP ${response.status}`,
        );
      }

      const updated: Environment = await response.json();

      onUpdated(updated);
      setIsEditing(false);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Не удалось удалить среду.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <article className="card">
      <h3>{environment.name}</h3>

      <p>
        Шаблон:{" "}
        {environment.template === "fastapi-postgres"
          ? "FastAPI + PostgreSQL"
          : environment.template === "nginx"
            ? "Nginx"
            : environment.template}
      </p>

      <p>Статус: {statusLabels[environment.status] ?? environment.status}</p>

      <p>ID: {environment.id}</p>

      {environment.template === "fastapi-postgres" &&
        environment.status !== "deleting" && (
          <p className="environment-hint">
            При удалении этой среды том PostgreSQL и все данные в нём будут
            удалены безвозвратно.
          </p>
        )}

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
            disabled={isSubmitting || environment.status === "deploying"}
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
