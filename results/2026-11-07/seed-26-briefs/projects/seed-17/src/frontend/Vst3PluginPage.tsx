// src/frontend/Vst3PluginPage.tsx
import { useEffect, useState } from "react";

export const route = "/vst3_plugins";

type Row = { id: number; title: string };

export function Vst3PluginPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/vst3_plugins")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Vst3Plugin</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
