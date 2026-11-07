// src/frontend/PolicyPage.tsx
import { useEffect, useState } from "react";

export const route = "/policys";

type Row = { id: number; title: string };

export function PolicyPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/policys")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Policy</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
