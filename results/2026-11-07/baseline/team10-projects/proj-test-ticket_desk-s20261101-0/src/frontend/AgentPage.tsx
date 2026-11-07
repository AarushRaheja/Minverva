// src/frontend/AgentPage.tsx
import { useEffect, useState } from "react";

export const route = "/agents";

type Row = { id: number; title: string };

export function AgentPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/agents")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Agent</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
