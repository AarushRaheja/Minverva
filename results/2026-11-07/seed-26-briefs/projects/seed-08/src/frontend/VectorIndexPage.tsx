// src/frontend/VectorIndexPage.tsx
import { useEffect, useState } from "react";

export const route = "/vector_indices";

type Row = { id: number; title: string };

export function VectorIndexPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/vector_indexes")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>VectorIndex</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
