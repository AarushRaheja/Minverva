// src/frontend/BakerPage.tsx
import { useEffect, useState } from "react";

export const route = "/bakers";

type Row = { id: number; title: string };

export function BakerPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/bakers")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Baker</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
