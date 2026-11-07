// src/frontend/FeaturePage.tsx
import { useEffect, useState } from "react";

export const route = "/features";

type Row = { id: number; title: string };

export function FeaturePage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/features")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Feature</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
