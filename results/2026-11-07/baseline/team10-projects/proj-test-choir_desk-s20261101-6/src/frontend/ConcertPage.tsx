// src/frontend/ConcertPage.tsx
import { useEffect, useState } from "react";

export const route = "/concerts";

type Row = { id: number; title: string };

export function ConcertPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/concerts")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Concert</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
