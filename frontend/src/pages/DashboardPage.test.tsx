import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import DashboardPage from "./DashboardPage";

vi.mock("../auth/useAuth", () => ({
  useAuth: () => ({
    session: {
      token: "test-token",
      user: {
        id: 3,
        username: "frontendtester",
        email: "frontendtester@example.com",
        role: "developer",
        is_active: true,
      },
    },
    logout: vi.fn(),
  }),
}));

const pendingEnvironment = {
  id: 7,
  name: "polling-test-01",
  template: "nginx",
  status: "pending",
  host_port: null,
};

const runningEnvironment = {
  ...pendingEnvironment,
  status: "running",
  host_port: 60209,
};

function apiResponse(data: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => data,
  };
}

function renderDashboard() {
  return render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
  );
}

async function advanceTime(milliseconds: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(milliseconds);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Автоматическое обновление тестовых сред", () => {
  it("обновляет статус pending на running", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(apiResponse([pendingEnvironment]))
      .mockResolvedValueOnce(apiResponse([runningEnvironment]));

    vi.stubGlobal("fetch", fetchMock);

    renderDashboard();

    await advanceTime(0);

    expect(screen.getByText("Статус: Ожидает создания")).toBeInTheDocument();

    await advanceTime(5000);

    expect(screen.getByText("Статус: Работает")).toBeInTheDocument();

    const link = screen.getByRole("link", {
      name: "Открыть среду",
    });

    expect(link).toHaveAttribute("href", "http://127.0.0.1:60209");

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("убирает карточку после удаления среды", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(apiResponse([runningEnvironment]))
      .mockResolvedValueOnce(apiResponse([]));

    vi.stubGlobal("fetch", fetchMock);

    renderDashboard();

    await advanceTime(0);

    expect(screen.getByText("polling-test-01")).toBeInTheDocument();

    await advanceTime(5000);

    expect(screen.queryByText("polling-test-01")).not.toBeInTheDocument();

    expect(
      screen.getByText("У вас пока нет тестовых сред."),
    ).toBeInTheDocument();
  });

  it("останавливает опрос после закрытия страницы", async () => {
    const fetchMock = vi.fn().mockResolvedValue(apiResponse([]));

    vi.stubGlobal("fetch", fetchMock);

    const { unmount } = renderDashboard();

    await advanceTime(0);

    expect(fetchMock).toHaveBeenCalledTimes(1);

    unmount();

    await advanceTime(15000);

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
