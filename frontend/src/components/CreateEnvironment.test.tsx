import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CreateEnvironmentForm from "./CreateEnvironmentForm";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("CreateEnvironmentForm", () => {
  it("успешно создаёт тестовую среду", async () => {
    const user = userEvent.setup();
    const onCreated = vi.fn();

    const created = {
      id: 10,
      name: "test-nginx",
      template: "nginx",
      status: "pending",
    };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => created,
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<CreateEnvironmentForm token="test-token" onCreated={onCreated} />);

    await user.type(screen.getByLabelText("Название среды"), "test-nginx");

    await user.click(
      screen.getByRole("button", {
        name: "Создать среду",
      }),
    );

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Среда «test-nginx» создана.",
    );

    expect(onCreated).toHaveBeenCalledWith(created);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/environments",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          name: "test-nginx",
          template: "nginx",
        }),
        headers: expect.objectContaining({
          Authorization: "Bearer test-token",
        }),
      }),
    );
  });

  it("показывает ошибку при ответе 422", async () => {
    const user = userEvent.setup();
    const onCreated = vi.fn();

    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<CreateEnvironmentForm token="test-token" onCreated={onCreated} />);

    await user.type(screen.getByLabelText("Название среды"), "test-nginx");

    await user.click(
      screen.getByRole("button", {
        name: "Создать среду",
      }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Проверьте правильность имени среды.",
    );

    expect(onCreated).not.toHaveBeenCalled();
  });
});
