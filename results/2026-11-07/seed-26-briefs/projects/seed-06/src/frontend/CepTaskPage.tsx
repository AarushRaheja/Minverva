// src/frontend/CepTaskPage.tsx
import { useEffect, useState } from "react";

export const route = "/cep_tasks";

type Row = { id: number; title: string };

export function CepTaskPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/cep_tasks")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>CepTask</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
