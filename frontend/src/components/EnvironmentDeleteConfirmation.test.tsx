import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import EnvironmentCard from "./EnvironmentCard";
import type { Environment } from "../types/environment";

const environment: Environment = {
  id: 15,
  name: "my-fastapi-test",
  template: "fastapi-postgres",
  status: "running",
  host_port: 53000,
  delete_volume_on_delete: false,
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("FastAPI + PostgreSQL deletion", () => {
  it("requires confirmation and sends delete_volume=true", async () => {
    const user = userEvent.setup();
    const onUpdated = vi.fn();

    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(window, "prompt").mockReturnValue("my-fastapi-test");

    const updated = {
      ...environment,
      status: "deleting",
      delete_volume_on_delete: true,
    };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 202,
      json: async () => updated,
    });

    vi.stubGlobal("fetch", fetchMock);

    render(
      <EnvironmentCard
        environment={environment}
        token="test-token"
        onUpdated={onUpdated}
        onDeleted={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Удалить" }));

    await waitFor(() => {
      expect(onUpdated).toHaveBeenCalledWith(updated);
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/environments/15?delete_volume=true",
      expect.objectContaining({
        method: "DELETE",
        headers: {
          Authorization: "Bearer test-token",
        },
      }),
    );
  });

  it("does not send a request when confirmation is cancelled", async () => {
    const user = userEvent.setup();

    vi.spyOn(window, "confirm").mockReturnValue(false);

    const promptMock = vi.spyOn(window, "prompt").mockReturnValue(null);

    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(
      <EnvironmentCard
        environment={environment}
        token="test-token"
        onUpdated={vi.fn()}
        onDeleted={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Удалить" }));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(promptMock).not.toHaveBeenCalled();
  });

  it("rejects an incorrect environment name", async () => {
    const user = userEvent.setup();

    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(window, "prompt").mockReturnValue("wrong-name");

    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(
      <EnvironmentCard
        environment={environment}
        token="test-token"
        onUpdated={vi.fn()}
        onDeleted={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Удалить" }));

    expect(fetchMock).not.toHaveBeenCalled();

    expect(screen.getByRole("alert").textContent).toContain(
      "имя среды не совпадает",
    );
  });

  it("disables deletion during deployment", () => {
    render(
      <EnvironmentCard
        environment={{
          ...environment,
          status: "deploying",
        }}
        token="test-token"
        onUpdated={vi.fn()}
        onDeleted={vi.fn()}
      />,
    );

    const button = screen.getByRole("button", {
      name: "Удалить",
    }) as HTMLButtonElement;

    expect(button.disabled).toBe(true);
  });
});
