// src/frontend/TableTownPage.tsx
import { useEffect, useState } from "react";

export const route = "/table_towns";

type Row = { id: number; title: string };

export function TableTownPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/table_towns")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>TableTown</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
