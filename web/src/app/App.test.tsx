import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import fixture from "../test/report.fixture.json";
import { App } from "./App";

function serve(body: unknown, ok = true) {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve({ ok, status: ok ? 200 : 500, json: () => Promise.resolve(body) })),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("console", () => {
  it("shows a loading state, then a decision card with its path and evidence", async () => {
    serve(fixture);
    render(<App />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading the report");
    const path = await screen.findByRole("list", { name: "Why this card exists" });
    expect(within(path).getAllByRole("listitem").length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByRole("tab").length).toBeGreaterThanOrEqual(2);
  });

  it("switches sample cards", async () => {
    serve(fixture);
    render(<App />);
    const tab = await screen.findByRole("tab", { name: "Supplier in trouble" });
    await userEvent.click(tab);
    expect(tab).toHaveAttribute("aria-selected", "true");
    expect(within(screen.getByRole("tabpanel")).getByText("a year at risk")).toBeInTheDocument();
  });

  it("shows the comparison, the gates and an empty state when the held-out seeds have not run", async () => {
    serve({ ...fixture, heldout: null });
    render(<App />);
    expect(await screen.findByRole("table", { name: /Seeds 11, 12, 13/ })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Gates" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Held-out seeds, run once" }));
    expect(screen.getByText("The held-out seeds have not been run")).toBeInTheDocument();
  });

  it("explains a failed load and offers to try again", async () => {
    serve({}, false);
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("HTTP 500");
    expect(screen.getByRole("button", { name: "Load the report again" })).toBeInTheDocument();
  });

  it("treats a report without development results as an error", async () => {
    serve({ heldout: null });
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("no development results");
  });
});
