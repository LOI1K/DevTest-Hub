import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import AuthProvider from "../auth/AuthProvider";
import App from "../App";

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderApp(path = "/login") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("Авторизация DevTest Hub", () => {
  it("входит, открывает кабинет и выходит", async () => {
    const user = userEvent.setup();

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          access_token: "test-token",
          token_type: "bearer",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          id: 1,
          username: "frontendtester",
          email: "frontendtester@example.com",
          role: "developer",
          is_active: true,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      });

    vi.stubGlobal("fetch", fetchMock);

    renderApp();

    await user.type(screen.getByLabelText("Логин"), "frontendtester");

    await user.type(screen.getByLabelText("Пароль"), "test-password");

    await user.click(screen.getByRole("button", { name: "Войти" }));

    expect(
      await screen.findByRole("heading", {
        name: "Добро пожаловать, frontendtester!",
      }),
    ).toBeInTheDocument();

    const loginOptions = fetchMock.mock.calls[0][1] as RequestInit;
    const body = loginOptions.body as URLSearchParams;

    expect(body.get("username")).toBe("frontendtester");
    expect(body.get("password")).toBe("test-password");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/users/me",
      expect.objectContaining({
        headers: {
          Authorization: "Bearer test-token",
        },
      }),
    );

    await user.click(
      screen.getByRole("button", {
        name: "Выйти из аккаунта",
      }),
    );

    expect(
      await screen.findByRole("heading", {
        name: "Вход в аккаунт",
      }),
    ).toBeInTheDocument();
  });

  it("отклоняет неправильный пароль", async () => {
    const user = userEvent.setup();

    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
    });

    vi.stubGlobal("fetch", fetchMock);

    renderApp();

    await user.type(screen.getByLabelText("Логин"), "frontendtester");

    await user.type(screen.getByLabelText("Пароль"), "wrong-password");

    await user.click(screen.getByRole("button", { name: "Войти" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Неверный логин или пароль.",
    );

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("не открывает кабинет без авторизации", async () => {
    renderApp("/dashboard");

    expect(
      await screen.findByRole("heading", {
        name: "Вход в аккаунт",
      }),
    ).toBeInTheDocument();

    expect(screen.queryByText("Ваш профиль")).not.toBeInTheDocument();
  });
});
