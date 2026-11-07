// src/frontend/AudioTrackPage.tsx
import { useEffect, useState } from "react";

export const route = "/audio_tracks";

type Row = { id: number; title: string };

export function AudioTrackPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/audio_tracks")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>AudioTrack</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
