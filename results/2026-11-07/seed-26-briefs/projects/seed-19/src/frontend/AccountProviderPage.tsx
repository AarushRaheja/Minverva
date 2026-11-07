// src/frontend/AccountProviderPage.tsx
import { useEffect, useState } from "react";

export const route = "/account_providers";

type Row = { id: number; title: string };

export function AccountProviderPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/account_providers")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <section>
      <h1>AccountProvider</h1>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>{row.title}</li>
        ))}
      </ul>
    </section>
  );
}
