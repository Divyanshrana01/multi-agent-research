import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ReportBody from "../components/ReportBody/ReportBody";

describe("ReportBody", () => {
  it("renders markdown headings as real headings", () => {
    render(<ReportBody markdown={"## Key Findings\n\nSome text."} />);
    expect(screen.getByRole("heading", { name: "Key Findings" })).toBeInTheDocument();
  });

  it("treats the writer agent's bare 'Section:' lines as headings", () => {
    // the agent often emits these without any hashes
    render(<ReportBody markdown={"Executive Summary:\n\nThe body."} />);
    expect(screen.getByRole("heading", { name: "Executive Summary" })).toBeInTheDocument();
  });

  it("groups consecutive bullets into one list", () => {
    render(<ReportBody markdown={"- first\n- second\n- third"} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(screen.getAllByRole("list")).toHaveLength(1);
  });

  it("handles numbered lists too", () => {
    render(<ReportBody markdown={"1. first\n2. second"} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("renders bold and italic inline", () => {
    const { container } = render(<ReportBody markdown="Some **bold** and *italic* text." />);
    expect(container.querySelector("strong")).toHaveTextContent("bold");
    expect(container.querySelector("em")).toHaveTextContent("italic");
  });

  it("does not execute markup in model output", () => {
    // React builds the elements, so this must arrive as literal text
    const { container } = render(<ReportBody markdown={"<img src=x onerror=alert(1)>"} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<img src=x onerror=alert(1)>");
  });

  it("survives an empty report", () => {
    const { container } = render(<ReportBody markdown="" />);
    expect(container.firstChild).toBeEmptyDOMElement();
  });
});
