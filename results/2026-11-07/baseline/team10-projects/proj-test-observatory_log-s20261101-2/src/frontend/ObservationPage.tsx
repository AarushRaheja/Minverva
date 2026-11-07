// src/frontend/ObservationPage.tsx
import { useEffect, useState } from "react";

export const route = "/observations";

type Row = { id: number; title: string };

export function ObservationPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/observations")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Observation</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
