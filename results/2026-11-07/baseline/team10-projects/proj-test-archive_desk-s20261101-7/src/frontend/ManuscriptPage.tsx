// src/frontend/ManuscriptPage.tsx
import { useEffect, useState } from "react";

export const route = "/manuscripts";

type Row = { id: number; title: string };

export function ManuscriptPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/manuscripts")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Manuscript</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
