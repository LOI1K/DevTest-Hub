import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import CreateEnvironmentForm from "./CreateEnvironmentForm";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("CreateEnvironmentForm templates", () => {
  it("selects Nginx by default", () => {
    render(<CreateEnvironmentForm token="test-token" onCreated={vi.fn()} />);

    const select = screen.getByRole("combobox", {
      name: "Шаблон среды",
    }) as HTMLSelectElement;

    expect(select.value).toBe("nginx");

    const fastapiOption = screen.getByRole("option", {
      name: /FastAPI \+ PostgreSQL/,
    }) as HTMLOptionElement;

    expect(fastapiOption.disabled).toBe(true);
  });

  it("sends FastAPI template when feature is enabled", async () => {
    vi.stubEnv("VITE_ENABLE_FASTAPI_POSTGRES", "true");

    const created = {
      id: 15,
      name: "my-fastapi-test",
      template: "fastapi-postgres",
      status: "pending",
      host_port: null,
      delete_volume_on_delete: false,
    };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => created,
    });

    vi.stubGlobal("fetch", fetchMock);

    const onCreated = vi.fn();

    render(<CreateEnvironmentForm token="test-token" onCreated={onCreated} />);

    fireEvent.change(screen.getByLabelText("Название среды"), {
      target: { value: "my-fastapi-test" },
    });

    fireEvent.change(
      screen.getByRole("combobox", {
        name: "Шаблон среды",
      }),
      {
        target: { value: "fastapi-postgres" },
      },
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Создать среду",
      }),
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(onCreated).toHaveBeenCalledWith(created);
    });

    const [, options] = fetchMock.mock.calls[0];

    expect(JSON.parse(options.body)).toEqual({
      name: "my-fastapi-test",
      template: "fastapi-postgres",
    });
  });
});
