class PcmWorkletProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = [];
    this.targetRate = 16000;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;

    const channelData = input[0];
    const sourceRate = sampleRate;
    const ratio = sourceRate / this.targetRate;

    for (let i = 0; i * ratio < channelData.length; i++) {
      const srcIdx = i * ratio;
      const idx1 = Math.floor(srcIdx);
      const idx2 = Math.min(idx1 + 1, channelData.length - 1);
      const frac = srcIdx - idx1;
      const sample = channelData[idx1] * (1 - frac) + channelData[idx2] * frac;

      const clamped = Math.max(-1, Math.min(1, sample));
      const int16Sample = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
      this.buffer.push(int16Sample);
    }

    if (this.buffer.length >= 1600) {
      const pcm16 = new Int16Array(this.buffer.splice(0, 1600));
      this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
    }
    return true;
  }
}

registerProcessor("pcm-worklet-processor", PcmWorkletProcessor);
