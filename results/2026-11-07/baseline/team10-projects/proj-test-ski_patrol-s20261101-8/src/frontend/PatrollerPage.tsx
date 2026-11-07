// src/frontend/PatrollerPage.tsx
import { useEffect, useState } from "react";

export const route = "/patrollers";

type Row = { id: number; title: string };

export function PatrollerPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/patrollers")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Patroller</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
