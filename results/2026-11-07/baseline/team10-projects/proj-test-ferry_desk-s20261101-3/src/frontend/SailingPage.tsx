// src/frontend/SailingPage.tsx
import { useEffect, useState } from "react";

export const route = "/sailings";

type Row = { id: number; title: string };

export function SailingPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/sailings")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Sailing</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
