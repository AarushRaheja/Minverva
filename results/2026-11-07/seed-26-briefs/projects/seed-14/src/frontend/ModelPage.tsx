// src/frontend/ModelPage.tsx
import { useEffect, useState } from "react";

export const route = "/models";

type Row = { id: number; title: string };

export function ModelPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/models")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Model</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
