// src/frontend/VideoPage.tsx
import { useEffect, useState } from "react";

export const route = "/videos";

type Row = { id: number; title: string };

export function VideoPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/videos")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>Video</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
