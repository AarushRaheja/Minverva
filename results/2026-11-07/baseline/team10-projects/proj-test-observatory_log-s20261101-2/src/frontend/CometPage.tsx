// src/frontend/CometPage.tsx
import { useEffect, useState } from "react";

export const route = "/comets";

type Row = { id: number; title: string };

export function CometPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/comets")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Comet</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
