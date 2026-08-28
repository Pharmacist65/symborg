// Microphone capture as an AudioWorklet.
//
// ScriptProcessorNode runs on the main thread, so it stutters whenever the page does
// anything — and on a phone carried in a shirt pocket the page is doing things (waking,
// repainting, reconnecting). The worklet runs on the audio thread and keeps its timing
// through all of it.

class Capture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = [];
    this.filled = 0;
    this.target = 480;          // 20 ms at 24 kHz
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    const channel = input[0];

    const pcm = new Int16Array(channel.length);
    for (let i = 0; i < channel.length; i++) {
      const v = Math.max(-1, Math.min(1, channel[i]));
      pcm[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
    }
    this.buffer.push(pcm);
    this.filled += pcm.length;

    while (this.filled >= this.target) {
      const frame = new Int16Array(this.target);
      let at = 0;
      while (at < this.target) {
        const head = this.buffer[0];
        const take = Math.min(head.length, this.target - at);
        frame.set(head.subarray(0, take), at);
        at += take;
        if (take === head.length) this.buffer.shift();
        else this.buffer[0] = head.subarray(take);
      }
      this.filled -= this.target;
      this.port.postMessage(frame, [frame.buffer]);
    }
    return true;
  }
}

registerProcessor('capture', Capture);
