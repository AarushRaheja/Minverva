// src/frontend/DoughMixPage.tsx
import { useEffect, useState } from "react";

export const route = "/dough_mixes";

type Row = { id: number; title: string };

export function DoughMixPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/dough_mixes")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>DoughMix</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
