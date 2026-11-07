// src/frontend/DeviceForm.tsx
import { createDevice } from "../network/device_client";

export function DeviceForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createDevice({ title: "new device" });
      }}
    >
      <input name="title" placeholder="Device title" />
      <button type="submit">Save</button>
    </form>
  );
}
