import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EnvironmentCard from "./EnvironmentCard";

const environment = {
  id: 4,
  name: "crud-demo",
  template: "nginx",
  status: "pending",
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("EnvironmentCard", () => {
  it("изменяет название тестовой среды", async () => {
    const user = userEvent.setup();
    const onUpdated = vi.fn();
    const onDeleted = vi.fn();

    const updated = {
      ...environment,
      name: "crud-demo-updated",
    };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => updated,
    });

    vi.stubGlobal("fetch", fetchMock);

    render(
      <EnvironmentCard
        environment={environment}
        token="test-token"
        onUpdated={onUpdated}
        onDeleted={onDeleted}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Изменить" }));

    const input = screen.getByLabelText("Новое название");

    await user.clear(input);
    await user.type(input, "crud-demo-updated");

    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => {
      expect(onUpdated).toHaveBeenCalledWith(updated);
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/environments/4",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          name: "crud-demo-updated",
        }),
        headers: expect.objectContaining({
          Authorization: "Bearer test-token",
        }),
      }),
    );
  });


  it("помечает среду для удаления после подтверждения", async () => {
    const user = userEvent.setup();
    const onUpdated = vi.fn();
    const onDeleted = vi.fn();

    vi.spyOn(window, "confirm").mockReturnValue(true);

    const deletingEnvironment = {
      ...environment,
      status: "deleting",
    };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 202,
      json: async () => deletingEnvironment,
    });

    vi.stubGlobal("fetch", fetchMock);

    render(
      <EnvironmentCard
        environment={environment}
        token="test-token"
        onUpdated={onUpdated}
        onDeleted={onDeleted}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "Удалить" }),
    );

    await waitFor(() => {
      expect(onUpdated).toHaveBeenCalledWith(deletingEnvironment);
    });

    expect(onDeleted).not.toHaveBeenCalled();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/environments/4",
      expect.objectContaining({
        method: "DELETE",
        headers: {
          Authorization: "Bearer test-token",
        },
      }),
    );
  });
});
