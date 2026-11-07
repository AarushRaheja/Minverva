// src/frontend/CookPage.tsx
import { useEffect, useState } from "react";

export const route = "/cooks";

type Row = { id: number; title: string };

export function CookPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/cooks")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Cook</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
