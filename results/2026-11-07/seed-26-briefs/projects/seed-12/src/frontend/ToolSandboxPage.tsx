// src/frontend/ToolSandboxPage.tsx
import { useEffect, useState } from "react";

export const route = "/tool_sandboxes";

type Row = { id: number; title: string };

export function ToolSandboxPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/tool_sandboxes")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>ToolSandbox</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
