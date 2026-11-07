import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import EnvironmentCard from "./EnvironmentCard";
import type { Environment } from "../types/environment";

const environment: Environment = {
  id: 3,
  name: "my-first-nginx",
  template: "nginx",
  status: "running",
  host_port: 52368,
};

function renderCard(overrides: Partial<Environment> = {}) {
  render(
    <EnvironmentCard
      environment={{ ...environment, ...overrides }}
      token="test-token"
      onUpdated={vi.fn()}
      onDeleted={vi.fn()}
    />,
  );
}

describe("Открытие тестовой среды", () => {
  it("показывает ссылку для работающей среды", () => {
    renderCard();

    const link = screen.getByRole("link", {
      name: "Открыть среду",
    });

    expect(link).toHaveAttribute("href", "http://127.0.0.1:52368");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("не показывает ссылку для pending", () => {
    renderCard({ status: "pending" });

    expect(
      screen.queryByRole("link", {
        name: "Открыть среду",
      }),
    ).not.toBeInTheDocument();
  });

  it("не показывает ссылку без порта", () => {
    renderCard({ host_port: null });

    expect(
      screen.queryByRole("link", {
        name: "Открыть среду",
      }),
    ).not.toBeInTheDocument();
  });
});
