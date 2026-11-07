// src/frontend/TelescopePage.tsx
import { useEffect, useState } from "react";

export const route = "/telescopes";

type Row = { id: number; title: string };

export function TelescopePage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/telescopes")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Telescope</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
