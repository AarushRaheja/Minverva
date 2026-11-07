// src/frontend/NvmeDevicePage.tsx
import { useEffect, useState } from "react";

export const route = "/nvme_devices";

type Row = { id: number; title: string };

export function NvmeDevicePage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/nvme_devices")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>NvmeDevice</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
