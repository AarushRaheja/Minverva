// src/frontend/CellarPage.tsx
import { useEffect, useState } from "react";

export const route = "/cellars";

type Row = { id: number; title: string };

export function CellarPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/cellars")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Cellar</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
