// src/frontend/PipelinePage.tsx
import { useEffect, useState } from "react";

export const route = "/pipelines";

type Row = { id: number; title: string };

export function PipelinePage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/pipelines")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Pipeline</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
