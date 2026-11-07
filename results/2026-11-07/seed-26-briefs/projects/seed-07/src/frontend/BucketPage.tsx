// src/frontend/BucketPage.tsx
import { useEffect, useState } from "react";

export const route = "/buckets";

type Row = { id: number; title: string };

export function BucketPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/buckets")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Bucket</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
