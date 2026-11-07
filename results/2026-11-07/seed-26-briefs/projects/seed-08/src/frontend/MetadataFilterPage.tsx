// src/frontend/MetadataFilterPage.tsx
import { useEffect, useState } from "react";

export const route = "/metadata_filters";

type Row = { id: number; title: string };

export function MetadataFilterPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/metadata_filters")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>MetadataFilter</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
