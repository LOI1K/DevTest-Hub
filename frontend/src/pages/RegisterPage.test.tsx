import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import RegisterPage from "./RegisterPage";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("RegisterPage", () => {
  it("успешно регистрирует пользователя", async () => {
    const user = userEvent.setup();

    const registeredUser = {
      id: 10,
      username: "newdeveloper",
      email: "newdeveloper@example.com",
      role: "developer",
      is_active: true,
    };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => registeredUser,
    });

    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText("Логин"), "newdeveloper");

    await user.type(screen.getByLabelText("Email"), "newdeveloper@example.com");

    await user.type(screen.getByLabelText("Пароль"), "Test-Password-2026!");

    await user.click(
      screen.getByRole("button", {
        name: "Зарегистрироваться",
      }),
    );

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Пользователь newdeveloper зарегистрирован!",
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/auth/register",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          username: "newdeveloper",
          email: "newdeveloper@example.com",
          password: "Test-Password-2026!",
        }),
      }),
    );

    expect(screen.getByLabelText("Пароль")).toHaveValue("");
  });

  it("показывает ошибку при повторной регистрации", async () => {
    const user = userEvent.setup();

    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
    });

    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText("Логин"), "newdeveloper");

    await user.type(screen.getByLabelText("Email"), "newdeveloper@example.com");

    await user.type(screen.getByLabelText("Пароль"), "Test-Password-2026!");

    await user.click(
      screen.getByRole("button", {
        name: "Зарегистрироваться",
      }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Логин или email уже зарегистрирован.",
    );
  });
});
