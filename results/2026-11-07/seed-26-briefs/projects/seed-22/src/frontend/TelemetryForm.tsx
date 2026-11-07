// src/frontend/TelemetryForm.tsx
import { createTelemetry } from "../network/telemetry_client";

export function TelemetryForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createTelemetry({ title: "new telemetry" });
      }}
    >
      <input name="title" placeholder="Telemetry title" />
      <button type="submit">Save</button>
    </form>
  );
}
