// src/frontend/BarrelPage.tsx
import { useEffect, useState } from "react";

export const route = "/barrels";

type Row = { id: number; title: string };

export function BarrelPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/barrels")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Barrel</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
