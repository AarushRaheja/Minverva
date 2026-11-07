// src/frontend/DevicePage.tsx
import { useEffect, useState } from "react";

export const route = "/devices";

type Row = { id: number; title: string };

export function DevicePage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/devices")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Device</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
