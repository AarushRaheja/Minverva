// src/frontend/HarborPage.tsx
import { useEffect, useState } from "react";

export const route = "/harbors";

type Row = { id: number; title: string };

export function HarborPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/harbors")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Harbor</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
