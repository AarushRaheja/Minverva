// src/frontend/AudioTrackForm.tsx
import { createAudioTrack } from "../network/audio_track_client";

export function AudioTrackForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createAudioTrack({ title: "new audio_track" });
      }}
    >
      <input name="title" placeholder="AudioTrack title" />
      <button type="submit">Save</button>
    </form>
  );
}
