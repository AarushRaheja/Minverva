// src/frontend/VesselForm.tsx
import { createVessel } from "../network/vessel_client";

export function VesselForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createVessel({ title: "new vessel" });
      }}
    >
      <input name="title" placeholder="Vessel title" />
      <button type="submit">Save</button>
    </form>
  );
}
