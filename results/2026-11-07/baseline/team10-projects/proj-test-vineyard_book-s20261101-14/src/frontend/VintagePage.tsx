// src/frontend/VintagePage.tsx
import { useEffect, useState } from "react";

export const route = "/vintages";

type Row = { id: number; title: string };

export function VintagePage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/vintages")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Vintage</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
