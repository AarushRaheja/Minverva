// src/frontend/NvmeDeviceForm.tsx
import { createNvmeDevice } from "../network/nvme_device_client";

export function NvmeDeviceForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createNvmeDevice({ title: "new nvme_device" });
      }}
    >
      <input name="title" placeholder="Device title" />
      <button type="submit">Save</button>
    </form>
  );
}
