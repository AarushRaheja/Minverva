// src/frontend/AstronomerPage.tsx
import { useEffect, useState } from "react";

export const route = "/astronomers";

type Row = { id: number; title: string };

export function AstronomerPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/astronomers")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Astronomer</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
