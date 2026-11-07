// src/frontend/VideoForm.tsx
import { createVideo } from "../network/video_client";

export function VideoForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createVideo({ title: "new video" });
      }}
    >
      <input name="title" placeholder="Video title" />
      <button type="submit">Save</button>
    </form>
  );
}
