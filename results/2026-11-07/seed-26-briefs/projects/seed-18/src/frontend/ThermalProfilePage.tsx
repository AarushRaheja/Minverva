// src/frontend/ThermalProfilePage.tsx
import { useEffect, useState } from "react";

export const route = "/thermal_profiles";

type Row = { id: number; title: string };

export function ThermalProfilePage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/thermal_profiles")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>ThermalProfile</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
