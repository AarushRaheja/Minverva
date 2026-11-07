// src/network/audio_track_client.ts
export type AudioTrack = { id: number; title: string };

type NewAudioTrack = Omit<AudioTrack, "id">;

export async function listAudioTrack(): Promise<AudioTrack[]> {
  const res = await fetch("/api/audio_tracks");
  return res.json();
}

export async function createAudioTrack(payload: NewAudioTrack): Promise<AudioTrack> {
  const res = await fetch("/api/audio_tracks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
