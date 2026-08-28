// The same gate as providers/vad.py, in the browser.
//
// It has to run here rather than on the server: audio that never leaves the phone costs
// nothing to send and nothing to transcribe, and a room is mostly silent. Measured on a
// quiet room it passes under 40% and falling.
//
// Every threshold leans the same way as the Python one — cutting a word is expensive,
// passing a second of noise is not.

export const FRAME_MS = 20;
export const HANGOVER_MS = 900;   // a Turkish clause pauses before its final verb
export const LEAD_IN_MS = 300;    // the first consonant is quieter than the vowel
const FLOOR_ALPHA = 0.02;         // slow: a passing lorry must not raise the floor
const SPEECH_OVER_FLOOR = 3.2;
const MIN_FLOOR = 60;

export class Gate {
  constructor(sampleRate = 24000) {
    this.sampleRate = sampleRate;
    this.reset();
  }

  reset() {
    this.floor = MIN_FLOOR;       // start low, not at whatever arrives first
    this.quietMs = 10000;
    this.lead = [];
    this.leadMs = 0;
    this.passedMs = 0;
    this.heldMs = 0;
  }

  get speaking() { return this.quietMs < HANGOVER_MS; }

  get passedFraction() {
    const total = this.passedMs + this.heldMs;
    return total ? this.passedMs / total : 0;
  }

  // Takes Int16Array, returns Int16Array to send or null to hold back.
  filter(pcm) {
    if (!pcm || !pcm.length) return null;
    const ms = Math.round(1000 * pcm.length / this.sampleRate);

    let sum = 0;
    for (let i = 0; i < pcm.length; i++) sum += pcm[i] * pcm[i];
    const energy = Math.sqrt(sum / pcm.length);

    const loud = energy > Math.max(this.floor * SPEECH_OVER_FLOOR, MIN_FLOOR * 1.5);
    if (loud) {
      this.quietMs = 0;
    } else {
      this.quietMs += ms;
      // The floor only learns from quiet, or a long speaker teaches it that their own
      // voice is the background and it closes on them mid-sentence.
      this.floor += FLOOR_ALPHA * (energy - this.floor);
      if (this.floor < 1) this.floor = 1;
    }

    if (!this.speaking) {
      this.heldMs += ms;
      this.lead.push(pcm);
      this.leadMs += ms;
      while (this.leadMs > LEAD_IN_MS && this.lead.length > 1) {
        const dropped = this.lead.shift();
        this.leadMs -= Math.round(1000 * dropped.length / this.sampleRate);
      }
      return null;
    }

    this.passedMs += ms;
    if (this.lead.length) {
      const total = this.lead.reduce((n, p) => n + p.length, 0) + pcm.length;
      const merged = new Int16Array(total);
      let at = 0;
      for (const p of this.lead) { merged.set(p, at); at += p.length; }
      merged.set(pcm, at);
      this.lead = [];
      this.leadMs = 0;
      return merged;
    }
    return pcm;
  }
}
