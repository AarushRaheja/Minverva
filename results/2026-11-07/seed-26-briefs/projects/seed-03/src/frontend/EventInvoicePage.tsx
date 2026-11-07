// src/frontend/EventInvoicePage.tsx
import { AuthRequired } from "./AuthRequired";

export const route = "/accounts";

export function EventInvoicePage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    fetch("/api/event_invoices")
      .then((res) => res.json())
      .then(setRows);
  }, []);

  return (
    <AuthRequired>
      <section>
        <h1>EventInvoice</h1>
        <ul>
          {rows.map((row) => (
            <li key={row.id}>{row.title}</li>
          ))}
        </ul>
      </section>
    </AuthRequired>
  );
}
