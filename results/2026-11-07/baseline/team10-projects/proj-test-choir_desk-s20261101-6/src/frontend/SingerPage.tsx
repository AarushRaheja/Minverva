// src/frontend/SingerPage.tsx
import { useEffect, useState } from "react";

export const route = "/singers";

type Row = { id: number; title: string };

export function SingerPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/singers")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Singer</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
