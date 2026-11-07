// src/frontend/BelayCheckPage.tsx
import { useEffect, useState } from "react";

export const route = "/belay_checks";

type Row = { id: number; title: string };

export function BelayCheckPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/belay_checks")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>BelayCheck</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
