import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import PlatformCard from "./PlatformCard";

describe("PlatformCard", () => {
  it("показывает реализованный компонент", () => {
    render(
      <PlatformCard
        title="REST API"
        description="Серверная часть платформы"
        status="ready"
      />,
    );

    expect(
      screen.getByRole("heading", { name: "REST API" }),
    ).toBeInTheDocument();

    expect(screen.getByText("Реализовано")).toBeInTheDocument();
  });

  it("показывает запланированный компонент", () => {
    render(
      <PlatformCard
        title="Docker Worker"
        description="Развёртывание контейнеров"
        status="planned"
      />,
    );

    expect(screen.getByText("В разработке")).toBeInTheDocument();
  });
});
